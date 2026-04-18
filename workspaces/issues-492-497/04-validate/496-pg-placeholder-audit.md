# GH #496 — kailash-py PostgreSQL Placeholder Audit

Cross-SDK alignment review of kailash-rs#403 (codegen emitted `?` where `$N` is required for asyncpg). This audit verifies the kailash-py raw-SQL DDL/migration paths against `rules/dataflow-identifier-safety.md` AND placeholder-style correctness for the active driver.

## Audit Table

| path:line                                                                              | category                                                                                                                      | placeholder style                                                                             | verdict                                                                                                                                                                                        |
| -------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `migrations/batched_migration_executor.py:560,578,589,607,609,619,707,716,721,734,738` | Pre-built DDL strings (executor consumes a `sql_statements: List[str]` arg; no params bound at this layer)                    | N/A — no parameters at this site                                                              | PASS placeholder-style; **FAIL identifier validation** (caller responsibility, not validated here — see Note A)                                                                                |
| `migrations/sync_ddl_executor.py:284`                                                  | `execute_query(sql, params)` — used by the diagnostic SELECTs at L322-336 (`table_exists`) and L364-374 (`get_table_columns`) | psycopg2 `%s` (PG), aiosqlite `?` (SQLite), PyMySQL `%s` (MySQL) — driver-correct per dialect | PASS                                                                                                                                                                                           |
| `migrations/sync_ddl_executor.py:377`                                                  | `PRAGMA table_info({table_name})` — SQLite identifier interpolated into DDL                                                   | DDL-only, no VALUES                                                                           | **FAIL identifier validation** — raw f-string interpolation, no `_validate_identifier()` / `quote_identifier()` (HIGH per `dataflow-identifier-safety.md` MUST 1)                              |
| `core/engine.py:6150,6155`                                                             | Migration execution; consumes pre-built `sql` string from `_generate_migration_sql()`                                         | N/A — no params bound at execution site                                                       | PASS placeholder-style; identifier validation is responsibility of generator (see Note B)                                                                                                      |
| `core/engine.py:6242,6248,6263,6266` (`_generate_migration_sql`)                       | Migration codegen for ADD COLUMN / DROP COLUMN / MODIFY COLUMN                                                                | DDL-only, no VALUES placeholders                                                              | **FAIL identifier validation** — `table_name`, `column_name`, `new_type` interpolated raw into DDL via f-string with no `quote_identifier()` (HIGH per `dataflow-identifier-safety.md` MUST 1) |
| `nodes/transaction_nodes.py:361` (`SAVEPOINT "{name}"`)                                | Identifier interpolation into transaction control statement                                                                   | DDL-adjacent, no VALUES                                                                       | PASS — `savepoint_name` validated by inline regex `^[A-Za-z_][A-Za-z0-9_]{0,62}$` at L353 BEFORE interpolation. Matches `dataflow-identifier-safety.md` MUST 2 baseline regex + length check.  |
| `nodes/transaction_nodes.py:439` (`ROLLBACK TO SAVEPOINT "{name}"`)                    | Identifier interpolation                                                                                                      | DDL-adjacent, no VALUES                                                                       | PASS — same regex validation applied at L431 BEFORE interpolation.                                                                                                                             |

**Note A** (`batched_migration_executor.py`): the executor receives a fully-rendered `sql_statements: List[str]` from upstream. The placeholder-style burden falls on the producer of those strings, not this layer. No FAIL recorded against this file for placeholder mismatch.

**Note B** (`engine.py:6150,6155`): same — the execution sites consume the already-rendered SQL from `_generate_migration_sql()`. Identifier validation belongs at the generator (rows above).

## Cross-SDK Equivalent Of kailash-rs#403

kailash-rs#403 was a placeholder-style mismatch (`?` vs `$N`). The **kailash-py codegen does NOT have this bug**: the inspected migration codegen (`engine.py::_generate_migration_sql`) emits pure DDL with NO parameter placeholders — values like `new_type` and column metadata are interpolated as identifiers/types, not as bound parameters. The diagnostic SELECTs in `sync_ddl_executor.py` use the dialect-correct placeholder per driver (`%s` for psycopg2/PyMySQL, `?` for aiosqlite). Driver-detection happens at L322-336 via `self._db_type`.

## Bugs Found

Two HIGH-severity identifier-validation gaps (`dataflow-identifier-safety.md` MUST 1) — NOT placeholder-style bugs:

1. **`sync_ddl_executor.py:377`** — `PRAGMA table_info({table_name})` raw interpolation. SQLite-only path, but `table_name` flows from `get_table_columns(table_name)` whose call sites include schema-state diff machinery that may receive model-derived names. No `_validate_identifier()`.
2. **`engine.py:6242,6248,6263,6266`** — `_generate_migration_sql` interpolates `table_name`, `column_name`, `new_type` raw into ADD/DROP/MODIFY DDL. `column_name` and `table_name` originate from `MigrationOperation.details` (model registry-derived) and `_class_name_to_table_name()`; `new_type` originates from `details["changes"]["new_type"]` — caller-influenced. None route through `dialect.quote_identifier()`. Per `dataflow-identifier-safety.md` MUST 5, even if today's call paths are model-registry-only, a future refactor that loads operations from JSON or accepts a user-supplied alter spec re-opens the injection vector with no test signal.

## Final Verdict

**2-BUGS-FOUND (HIGH severity, identifier-validation class — not the kailash-rs#403 placeholder class)**

The kailash-rs#403 placeholder-mismatch bug does NOT exist in kailash-py — driver-correct placeholders are used in all parameter-binding sites inspected. However, the audit surfaced two pre-existing HIGH-severity DDL identifier-validation gaps that would survive into a future refactor.

## GH Issues To File (sharded per `autonomous-execution.md`)

Two separate issues — distinct files, distinct call paths, can be fixed in parallel worktrees:

1. **`fix(dataflow): route SQLite PRAGMA table_info table_name through quote_identifier (sync_ddl_executor.py:377)`** — single-line interpolation; add `_validate_identifier(table_name)` before the f-string. Tier 2 regression test with injection payloads per `dataflow-identifier-safety.md` MUST 3.
2. **`fix(dataflow): route _generate_migration_sql DDL identifiers through quote_identifier (core/engine.py:6242-6266)`** — four interpolation sites for ADD/DROP/MODIFY COLUMN. Validate `table_name`, `column_name`; reject malformed `new_type` via type allowlist (separate concern from identifier regex). Tier 2 regression test asserting injection payloads in `MigrationOperation.details["column_name"]` are rejected.

Both issues should carry the `cross-sdk` label and reference kailash-rs#403 as the cross-SDK origin (per `cross-sdk-inspection.md` MUST 2), even though the kailash-py findings are NOT the same bug class — the audit was triggered by the kailash-rs ticket and the relationship belongs in the issue body.
