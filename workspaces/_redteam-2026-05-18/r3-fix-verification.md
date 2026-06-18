# Round 3 — Fix Verification & Convergence Audit

Working-tree edits made in response to Round 2 findings. No commits yet (per brief).

## Method

For each landed fix: grep / Read confirms the code change accomplishes the claim; pytest exercises the path against real (sqlite) infra; cross-grep sweeps for adjacent same-bug-class gaps.

## Findings

| SEV | finding | file:line | evidence-command + output | recommended fix |
| --- | ------- | --------- | ------------------------- | --------------- |

(no new CRIT / HIGH / MED / LOW surfaced — all checks below resolved clean.)

---

## Verification — HIGH fix (`TransactionScope.execute_raw` protection routing)

### V1 — `_classify_raw_sql_operation` exists and maps correctly

Command:

```
grep -n "_classify_raw_sql_operation\|_execute_raw_with_protection" \
  packages/kailash-dataflow/src/dataflow/features/transactions.py
```

Output (excerpted):

```
41:def _classify_raw_sql_operation(sql: str) -> str:
85:async def _execute_raw_with_protection(
105:        operation = _classify_raw_sql_operation(sql)
274:        return await _execute_raw_with_protection(   # TransactionScope.execute_raw
761:            _execute_raw_with_protection(            # SyncTransactionScope.execute_raw
```

Read of `_classify_raw_sql_operation` (lines 41–82) confirms mapping:

- `SELECT/WITH/SHOW/EXPLAIN/VALUES/TABLE` → `"read"` (line 70)
- `INSERT → "create"`, `UPDATE → "update"`, `DELETE → "delete"`, `UPSERT → "upsert"` (lines 72–79)
- default → `"custom_query"` (line 82) — fail-closed for unknown leading keyword AND for empty/whitespace SQL (line 68)

Read of `_execute_raw_with_protection` (lines 85–133) confirms:

- Pulls `_protection_engine` off the dataflow instance (line 102) — mirrors `DataFlowExpress._check_protection_if_enabled`
- Calls `protection_engine.check_operation(operation=<classified>, model_name=None, connection_string=db.database_url, context={"surface": "transactions.execute_raw"})` BEFORE dispatching (lines 108–113)
- Then dispatches to asyncpg-vs-aiosqlite path correctly (lines 118–133)

**PASS** — the helper accomplishes what it claims.

### V2 — `dataflow_instance` plumbed at every constructor call site

Command:

```
grep -n "dataflow_instance=" packages/kailash-dataflow/src/dataflow/features/transactions.py
```

Output:

```
89:    dataflow_instance: Optional[Any],         # helper signature
171:        dataflow_instance: Optional[Any] = None,   # async TransactionScope ctor
277:            dataflow_instance=self._dataflow_instance,   # async execute_raw call
404:                dataflow_instance=self.dataflow,         # async TransactionManager.begin()
466:                dataflow_instance=self.dataflow,         # async _savepoint()
684:        dataflow_instance: Optional[Any] = None,   # SyncTransactionScope ctor
764:                dataflow_instance=self._dataflow_instance,   # sync execute_raw call
1019:            dataflow_instance=self._transactions.dataflow,   # SyncTransactionManager.begin()
```

Every constructor call (`TransactionScope(...)` at 399, `_savepoint` at 460, `SyncTransactionScope(...)` at 1014) passes `dataflow_instance` — no silent-None drift.

**PASS** — plumbing complete.

### V3 — Regression test collects + sync test passes

Command:

```
PYTHONPATH=src:packages/kailash-dataflow/src python -m pytest \
  packages/kailash-dataflow/tests/integration/test_issue_1083_followup_transactions_execute_raw_protection.py \
  --collect-only -q
```

Output: `5 tests collected in 0.15s` (4 async + 1 sync — matches brief).

Command:

```
PYTHONPATH=src:packages/kailash-dataflow/src python -m pytest \
  packages/kailash-dataflow/tests/integration/test_issue_1083_followup_transactions_execute_raw_protection.py::TestSyncTransactionsExecuteRawProtection::test_sync_execute_raw_blocks_delete_under_read_only -v
```

Output: `1 passed in 19.57s`

**PASS** — sync execute_raw is genuinely protection-routed against real sqlite.

### V4 — No-regression on #1050 mutation matrix

Command:

```
PYTHONPATH=src:packages/kailash-dataflow/src timeout 120 python -m pytest \
  packages/kailash-dataflow/tests/integration/test_issue_1050_protection_mutation_matrix.py -k sqlite
```

Output: 9 PASSED visible (create/update/delete/upsert + bulk\_\* + read_not_blocked), 0 FAILED, 0 ERROR; background exit code 0.

**PASS** — protection.py observability edit does not regress the existing #1050 matrix.

### V5 — Same-bug-class adjacent-gap sweep

Command (other raw-SQL entry points in DataFlow):

```
grep -rn "execute_raw\|raw_sql\|raw_query" packages/kailash-dataflow/src --include="*.py"
```

Two adjacent surfaces examined:

1. **`LightweightPool.execute_raw(sql)`** at `packages/kailash-dataflow/src/dataflow/core/pool_lightweight.py:152`. Read of lines 140–190: surface is hard-restricted to an allowlist (`SELECT 1`, `SELECT 'ok'`, `SHOW MAX_CONNECTIONS`, `SHOW SERVER_VERSION`, `SELECT version()`, `SELECT current_database()`, `SELECT pg_is_in_recovery()`) with a `ValueError` raised on any non-allowlist input (lines 182–190). No user-supplied SQL reaches the connection. Adjacent surface is structurally non-vulnerable to the #1083-class write bypass — no fix needed.

2. **`DataFlow.execute_raw(stmt)`** routed via `engine.execute_raw_lightweight` (line 9969) and `migration/security_definer.py:92`. Both call sites are migration-scope (numbered migration DDL execution) and route through the lightweight pool's allowlist OR through DataFlow's already-protected raw-SQL path. No bypass.

Command (other `conn.execute / conn.fetch` sites in transactions.py):

```
grep -n "conn\.execute\|conn\.fetch" packages/kailash-dataflow/src/dataflow/features/transactions.py
```

Output (excerpted): lines 397, 410, 421, 458, 471, 476, 616, 619, 624, 629 — every match outside the new `_execute_raw_with_protection` helper is a control statement (`BEGIN`/`COMMIT`/`ROLLBACK`/`SAVEPOINT`/`RELEASE SAVEPOINT`), NOT user-supplied SQL. Per brief: these are correctly outside scope.

**PASS** — no same-bug-class gap remaining in the user-supplied-SQL surface.

---

## Verification — MED-reviewer-2 fix (`specs/_index.md` row for dataflow-protection.md)

Command:

```
grep -c "dataflow-protection.md" specs/_index.md
```

Output: `1`

Command:

```
grep -n "dataflow-protection" specs/_index.md
```

Output:

```
22:| [dataflow-protection.md](dataflow-protection.md) | ProtectedDataFlow write-protection invariants I1-I9, OperationType enum, check_operation routing, async-hot-path wiring (#1050/#1058 closure baseline) |
```

Read of `specs/dataflow-protection.md:1–30` confirms description fidelity: spec is the authority for ProtectedDataFlow contracts (read-only, production_safe, business_hours, model/field protection), `WriteProtectionEngine.check_operation` enforcement, and OperationType mapping. Description accurately summarizes spec content; no phantom citation per `spec-accuracy.md` Rule 1.

**PASS** — spec is now discoverable via `_index.md` lookup.

---

## Verification — LOW-3-reviewer fix (observability schema-hash)

Command:

```
grep -n "schema_hash\|hashlib" packages/kailash-dataflow/src/dataflow/core/protection.py
```

Output:

```
8:import hashlib
243:        schema_hash = hashlib.sha256(schema_identifier.encode("utf-8")).hexdigest()[:8]
249:                "schema_hash": schema_hash,
```

Read of `protection.py:220–252` confirms:

- Raw `model` / `field` strings are kept ONLY in the process-local `self.events.append(event)` dict (lines 228–238) — used for in-process audit, never shipped to log aggregators.
- The structured `logger.warning("protection.protection_violation", ...)` payload (lines 244–252) emits ONLY `operation`, `level`, `schema_hash` (8-char sha256 of `model.field`), and `connection`. NO raw model/field name in the WARN extra dict.

This complies with `observability.md` Rule 8: "Schema-Revealing Field Names MUST Be DEBUG Or Hashed" — the hash form is the explicitly-mandated WARN-level alternative.

**PASS** — schema-revealing names no longer bleed to aggregators.

---

## Round 3 verification verdict: 0 CRIT / 0 HIGH / 0 MED / 0 LOW

NEW findings (not present in R1 or R2): 0

Fixes verified:

- **HIGH** (`transactions.execute_raw` protection routing): **PASS** — helper exists, classifier correct, plumbing complete, sync regression test PASSES against real sqlite (1 passed in 19.57s), no #1050 regression
- **MED** (`specs/_index.md` row): **PASS** — row added at line 22, description accurate against `specs/dataflow-protection.md:1–30`
- **LOW-3** (observability schema-hash): **PASS** — `hashlib` imported, 8-char sha256 emitted at WARN, raw schema names confined to process-local `events` dict

Adjacent-surface sweep: `pool_lightweight.execute_raw` is allowlist-restricted (structurally non-vulnerable to write bypass); other `conn.execute` sites in transactions.py are control statements only — no new same-bug-class gaps.

Convergence: **YES** (R3 zero new CRIT/HIGH AND all three fixes verified against working-tree state)
