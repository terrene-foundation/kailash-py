# Audit 06 — Nodes, Query, Migrations, Validation

**Scope**: `packages/kailash-dataflow/src/dataflow/{nodes,query,migrations,migration,validation,validators,classification,optimization}/`

**Auditor**: dataflow-specialist (Subsystem 06)
**Date**: 2026-04-08
**Posture**: uncompromising — per mandate, "DataFlow MUST be perfect".

All citations are `file:line` against the working tree at the head of `feat/platform-architecture-convergence`.

---

## 1. Executive summary

The CRUD node generator in `core/nodes.py` is largely safe (whitelist-driven field ordering), but everything orbiting it — every standalone bulk node, the query builder's identifier/limit handling, the `features.TransactionManager`, the `DynamicUpdateNode`, the auto-migrate boot sequence, the classification engine, and the two parallel migration + validation subtrees — is broken, dead, or actively dangerous.

Critical failures discovered:

- **CRITICAL-01**: `nodes/dynamic_update.py:172,182` is an unrestricted `exec()` on a node parameter. This is the RCE the security auditor flagged; no consumer anywhere in the tree references it. It exists only as an attack surface.
- **CRITICAL-02**: `nodes/bulk_update.py` and `nodes/bulk_delete.py` build SQL by f-string interpolation of **user-supplied field names, IDs, and values**. Every line from `bulk_update.py:344` through `:599` and `bulk_delete.py:297` through `:486` is a SQL injection vector. The defense — `value.replace("'", "''")` — is insufficient under non-default PostgreSQL settings and does nothing for identifiers, numeric values, or `record_id`.
- **CRITICAL-03**: `nodes/bulk_create.py:391-446` builds INSERT statements as f-strings, interpolating both column identifiers (line 420: `column_names` from `processed_data[0].keys()`) and escaped string literals. An attacker with control over `data[0]`'s dict keys controls the SQL.
- **CRITICAL-04**: `core/nodes.py:2192,2195,2235,2248` — in the generated `UpdateNode` path, **user-supplied `fields` dict keys are interpolated as SQL identifiers without any whitelist check against `self.model_fields`**. A caller passing `fields={"nonexistent_col; DROP TABLE--": 1}` gets direct injection. No operator, method, or branch validates field names against the model schema in the update path. Compare to the create path (`:1336-1344`) which is safe.
- **CRITICAL-05**: `database/query_builder.py:311-313` inlines `limit_value` and `offset_value` into SQL as raw literals: `limit_clause = f"LIMIT {self.limit_value}"`. Values flow from the node parameter without coercion; a string limit injects SQL. And there is **no upper cap on `limit`** anywhere in the code path — `core/nodes.py:2514` accepts whatever the caller passes.
- **CRITICAL-06**: `features/transactions.py:11-78` is a **fiction**. `TransactionManager.transaction()` is a Python context manager around a dict. No `BEGIN`, no `COMMIT`, no `ROLLBACK`, no connection. `core/engine.py:453` instantiates this fake on every `DataFlow()` init and `engine.py:2825` exposes it as `db.transactions`. Callers using `with db.transactions.transaction()` get atomicity that exists only in memory. This is a data-integrity lie.
- **CRITICAL-07**: `nodes/bulk_create.py:378-389` auto-injects `created_at`/`updated_at` into every record with `datetime.utcnow()`. `nodes/bulk_update.py:402-403` injects the magic string `"CURRENT_TIMESTAMP"` into `update_dict` then splices it raw into SQL. Both violate the project mandate that timestamps are auto-managed at the adapter layer. The magic-string branch is itself an injection vector: any caller who passes a literal string `"CURRENT_TIMESTAMP"` for a field value gets that string inlined as raw SQL.
- **CRITICAL-08**: `migrations/auto_migration_system.py:1637-1753`, invoked from `core/engine.py:5191-5196` with `interactive=False, auto_confirm=True`, runs DDL on first DataFlow construction **without human confirmation**. Failures are swallowed into `logger.error` + `return False, []` (line 5209-5212). The only schema validation runs inside the same auto-confirm path; there is no "dry-run first, then confirm" gate for production boot.
- **HIGH-01**: Forty-plus hardcoded `validate_queries=False` call sites (see `validate_queries` grep in § 5.5) disable the kailash core SDK's query validation layer on every SQL call made by DataFlow. This is a blanket opt-out with no per-call justification.

These are the critical eight. The rest of the subsystem is a quarry of HIGH- and MEDIUM-severity issues. Full list follows.

---

## 2. `nodes/dynamic_update.py` — RCE reimplementation (DELETE-ONLY)

### 2.1 Finding

`nodes/dynamic_update.py:147-223`. The class `DynamicUpdateNode.async_run()` takes two string parameters, `filter_code` and `prepare_code`, and passes them to Python's `exec()`:

- `:172` — `exec(self.filter_code, {}, namespace)`
- `:182` — `exec(self.prepare_code, {}, namespace)`

The "sandbox" is `globals={}` — this provides zero security. `__builtins__` is re-injected by Python automatically, and even without it, a literal-only environment gives full access via `().__class__.__mro__[1].__subclasses__()` and friends. Anyone with the ability to construct a DataFlow workflow from user-controllable input (any Nexus endpoint that deserializes a workflow JSON blob, any Kaizen agent that calls `workflow.add_node` with a parameter drawn from a tool output) can execute arbitrary Python on the DataFlow host.

This is a **covert reimplementation of kailash core's `PythonCodeNode`** which exists specifically to carry the safe-execution discipline. `dynamic_update.py` bypasses every gate that `PythonCodeNode` installs (no namespace restrictions, no compile-time whitelist, no `_getitem_` filtering, no import allowlist).

### 2.2 Reachability

`Grep("DynamicUpdateNode", dataflow/**)` returns exactly two hits:

1. `src/dataflow/nodes/dynamic_update.py` itself
2. `workspaces/dataflow-perfection/01-analysis/02-subsystem-audits/05-tenancy-and-security.md` (the parallel tenancy audit)

**Zero other consumers.** Not in tests. Not in examples. Not registered in `nodes/__init__.py:1-62`. The class defines itself, exposes `async_run`, and then... nothing. This is dead code that exists solely as an RCE surface.

### 2.3 Resolution

**Delete the file.** Delete imports. Delete any `NodeRegistry.register()` side-effect. Verify `nodes/__init__.py:1-62` is unchanged (it never referenced `DynamicUpdateNode` so deletion is trivially clean).

If a real DSL for "prepare then update" is wanted (it isn't — the existing `UpdateNode` + `fields` parameter already expresses it), build it on `PythonCodeNode` in the workflow layer, never as a DataFlow node with `exec()` in its body.

### 2.4 Severity

**CRITICAL**. RCE. Delete scope: 223 lines, one file. No migration path needed because no caller exists.

---

## 3. Generated CRUD nodes — `core/nodes.py` (3,771 lines)

There are no CreateNode/UpdateNode/ReadNode/DeleteNode/ListNode/BulkCreateNode files on disk. They are **generated at `@db.model` time by `NodeGenerator._create_node_class()`** (`core/nodes.py:279-281`) and registered into `NodeRegistry` plus `dataflow_instance._nodes`. The actual class body is an inline `class DataFlowNode(AsyncNode)` defined inside a closure. Every CRUD operation lives as a branch in the single `async_run(self, **kwargs)` method dispatched on a captured `operation` local.

This is already a design smell — 3,771 lines of generated class body means every change to any operation risks every other operation. But that's a MEDIUM for later. The issues below are severe enough on their own.

### 3.1 CreateNode — `core/nodes.py:1285-1678`

**Safe with caveats.**

- Line 1336-1344: `field_names` is built by iterating `model_fields.keys()` and filtering to known columns. This is a whitelist. The SQL at 1365/1368/1371 interpolates `columns` (a join of whitelisted names) and parameterized placeholders. **Not an injection vector.**
- Line 1338-1341: `id` is included only if the caller provided it. This was the fix for issue #42 (silent id drop). Regression risk: any future edit that loses the `elif name != "created_at", "updated_at"` guard at 1343 brings the regression back.
- Line 1498: `validate_queries=False` — see § 5.5.

Gotcha confirmed at line 1488-1491: `self._apply_tenant_isolation(query, values)` mutates query text with tenant filters. The injection path there is in the `_apply_tenant_isolation` implementation (scope of subsystem 05).

### 3.2 UpdateNode — `core/nodes.py:1960-2324`

**Multiple critical issues.**

**CRITICAL-04: SQL injection via `fields` dict keys.**

Flow:

1. Line 1977-1988: `filter_param = kwargs.get("filter")`, `fields_param = kwargs.get("fields")`. Fall back to deprecated `conditions`/`updates`.
2. Line 2107-2109: `if updates_dict: updates = updates_dict`. No validation of keys against `self.model_fields`.
3. Line 2192: `field_names = list(updates.keys())`. **Pure pass-through of caller-controlled dict keys.**
4. Line 2195: `set_clauses = [f"{name} = ${i + 1}" for i, name in enumerate(field_names)]`. The value is parameterized. The identifier is not.
5. Identical unsafe patterns on MySQL (line 2235) and SQLite (line 2248).

Proof-of-concept injection: a caller passing

```python
{"filter": {"id": 1}, "fields": {"name = 'pwned', password_hash": "x"}}
```

produces `UPDATE users SET name = 'pwned', password_hash = $1 WHERE id = $2`. Password is overwritten by `'pwned'` (a literal) and the supposed "password_hash" column is updated to "x". The only thing standing between DataFlow and a full account takeover is the bound parameter's column name lookup at the database layer (PostgreSQL will reject unknown columns, but crafting a valid injection is trivial — `UPDATE users SET password_hash = '' WHERE 1=1; --` via the identifier is also doable if the attacker just picks column names that exist).

**Silent parameter drop via fallback path.**

Lines 2110-2126 contain a backward-compat fallback:

```python
updates = {
    k: v
    for k, v in kwargs.items()
    if k not in [
        "record_id", "id", "database_url",
        "conditions", "updates", "filter", "fields",
    ]
    and k not in ["created_at", "updated_at"]
}
```

This means when the caller passes `{"filter": {"id": 1}, "Name": "x"}` (note the uppercase mistake, or any field that isn't in the canonical filter/fields/conditions/updates set, and isn't `record_id`/`id`/`database_url`), the fallback path collects `Name: "x"` and tries to update a column called `Name`. If `Name` is not a model column, the database rejects it. If it IS (SQLite is case-insensitive on some configurations), the update succeeds silently on an unrelated column. Either way, the call does NOT raise a `NodeValidationError` saying "unknown field". This is the silent parameter drop that `.claude/rules/testing.md` warns about.

**Auto-managed timestamp handling is split across two layers.**

- Lines 2125: `k not in ["created_at", "updated_at"]` excludes timestamps from the fallback collection, but
- Lines 2180-2189: `has_updated_at` is detected by introspection of the live table, and
- Lines 2199-2261: `updated_at_clause = "updated_at = CURRENT_TIMESTAMP"` is appended to the SET list.

This is correct for the auto-managed-timestamp promise _only if_ the model declares `updated_at`. If `updated_at` was renamed, dropped, or is optional, the detection at 2182-2189 silently falls back to `has_updated_at = False` and stops touching the column. No logging. This is a silent feature degradation — an operator running an online ALTER might see `updated_at` stop updating without any log signal.

**PostgreSQL `$N` parameter numbering collision.**

Lines 2195 and 2198: `WHERE id = ${len(field_names) + 1}`. The serializer concatenates update-values and `record_id` at 2268: `values = update_values + [record_id]`. This is consistent. But then line 2276 calls `self._apply_tenant_isolation(query, values)` which **adds more parameters to the query and re-writes placeholders**. If the tenant-isolation layer does not renumber `$N` placeholders consistently across the original query and its additions, you get off-by-one SQL at runtime. (Subsystem 05 has more on this.)

### 3.3 ListNode — `core/nodes.py:2513-2792`

**Multiple HIGH issues.**

- Line 2514: `limit = kwargs.get("limit", 10)`. **No upper bound.** `limit=10**9` flows to the database which allocates that many rows.
- Line 2515: `offset = kwargs.get("offset", 0)`. Same. A caller can request `offset=2**31`, forcing a full sequential scan.
- Line 2527-2531: if `order_by` is a string, it is `json.loads`-ed and otherwise reset to `[]`. A malformed order_by is silently dropped. Should raise.
- Line 2544-2554: the new `sort` parameter is copy-converted to `order_by`. The only validation of the `field` is `if field:` (truthy check). Unknown model fields are accepted; injection surface is inherited from the QueryBuilder (§ 4).
- Line 2610-2617: `for field, value in filter_dict.items()` passes `field` directly to `builder.where(...)`. No whitelist. Injection surface is inherited from the QueryBuilder.
- Line 2593-2597: `has_filters = "filter" in kwargs or has_soft_delete`. The auto-soft-delete filter at line 2581-2582 mutates `filter_dict` IN-PLACE by injecting `{"deleted_at": {"$null": True}}`. If a caller reused the same dict across two nodes (common in workflow graph wiring), the second node sees the mutation. Mutation-in-place on caller dicts is a bug source the project should ban project-wide.
- Line 2636: `builder.order_by("id", "DESC")` is the default. This is fine but forces a sort on every List call, which can be an O(n log n) trap on unindexed tables. Make it opt-out.

### 3.4 DeleteNode — `core/nodes.py:2326-2511`

- Line 2470: `validate_queries=False`.
- Line 2425-2464 (not shown in my read but inferred from the layout): deletion is by `record_id` via the same parameterized path as update. **Safe.**
- Absent feature: **no "affected rows must be ≤ N" sanity check**. A delete by filter could drop millions of rows with no warning.

### 3.5 UpsertNode / CountNode — `core/nodes.py:1063-1120`

Parameter definitions only; execution logic lives further down the dispatch. Not deeply audited; on-paper they look fine but carry the same `validate_queries=False` pattern.

### 3.6 BulkUpdateNode/BulkDeleteNode as branches of the generator

`core/nodes.py:3420-3581` contains in-line bulk update and bulk delete logic. Separate from `nodes/bulk_update.py` and `nodes/bulk_delete.py`. **Two parallel bulk implementations exist.** The generated branches use the model-field whitelist and parameterized queries (see line 3360 "inserted: records_processed"), while the standalone `nodes/bulk_update.py` files use unsafe f-string SQL construction (§ 5). Which one does a user actually get when they write `workflow.add_node("UserBulkUpdateNode", ...)`? The `NodeRegistry.register` call at line 272 registers the **generated** class, which shadows the standalone ones. So in the normal `@db.model` flow the safe branch runs. But in any code path that imports `nodes.bulk_update.BulkUpdateNode` directly (including the `@register_node` decorator at `nodes/bulk_update.py:13`), the **unsafe** class is registered globally and is reachable via workflow builders.

The right fix is to delete the standalone `nodes/bulk_*.py` files entirely. The logic is superseded.

---

## 4. `database/query_builder.py` — `QueryBuilder`

### 4.1 Injection via LIMIT/OFFSET

Lines 311-313:

```python
if self.limit_value is not None:
    limit_clause = f"LIMIT {self.limit_value}"
if self.offset_value is not None:
    limit_clause += f" OFFSET {self.offset_value}"
```

`self.limit_value` and `self.offset_value` are set by `QueryBuilder.limit(int)` and `QueryBuilder.offset(int)` at 215-223 **with no type check**. A caller passing `builder.limit("10; DROP TABLE users--")` produces `LIMIT 10; DROP TABLE users--`.

Fix: cast to `int(...)` and `max(0, min(n, MAX_LIMIT))` inside the setter, or parameterize the LIMIT/OFFSET (both PostgreSQL and MySQL accept `LIMIT $N OFFSET $N+1`; SQLite accepts `LIMIT ? OFFSET ?`).

### 4.2 Identifier quoting is non-escaping

Lines 441-453 `_quote_identifier`:

```python
if self.database_type == DatabaseType.POSTGRESQL:
    quoted_parts = [f'"{part}"' for part in parts]
elif self.database_type == DatabaseType.MYSQL:
    quoted_parts = [f"`{part}`" for part in parts]
else:  # SQLite
    quoted_parts = [f'"{part}"' for part in parts]
```

The code wraps the identifier in quote chars but does not escape embedded ones. `field = 'id" OR "1"="1'` becomes `"id" OR "1"="1"`. PostgreSQL treats the second quote as a string terminator and the rest as unquoted SQL. **Full injection.**

The correct escape is `part.replace('"', '""')` on PostgreSQL and `part.replace('`', '``')` on MySQL, then wrapping. Better still: whitelist identifiers against the model schema before they ever reach this function.

### 4.3 `$like` and `$regex` wildcard injection

- `_add_simple_condition` at line 110: `$like` with a user-supplied value. The value is parameterized, which prevents SQL injection. It does **not** prevent LIKE-wildcard abuse — user input `%` becomes a wildcard and widens the match; `_` matches any single character. A field that the model owner intended as an exact-match-with-wildcards-escaped will behave as a wildcard match.
- `_add_regex_condition` at line 161-177: `$regex` ships the user pattern to PostgreSQL's `~` operator or MySQL's `REGEXP`. **Catastrophic backtracking risk.** A single `(a+)+$` on a long string can hang the database connection. No length cap, no complexity check.

Fix: escape LIKE metacharacters by default (`value.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')`) and expose an `escape: bool = True` kwarg for callers that explicitly want wildcards. For `$regex`, apply a length cap (e.g. 256 chars) and reject catastrophic patterns with a timeout at the database side (`SET statement_timeout`).

### 4.4 Operator whitelist is good

Line 95-96: `if operator not in self.OPERATORS: raise ValueError(...)`. Unknown operators raise. This is correct per the mandate item 5. **Credit where due.**

### 4.5 `group_by` / `having` identifiers

- Line 248-253: `group_by` accepts field names, passes through `_quote_identifier`. Same injection as 4.2.
- Line 255-258 `having`: accepts **raw SQL strings** from the caller and appends them to the `HAVING` clause. `builder.having("1=1; DROP TABLE users--")` is a direct injection. This is by design — the type signature takes a string `condition`, not a structured clause — which means the caller has the responsibility. That is not acceptable in an engine-first framework. Either remove the method or require a structured condition (dict with whitelisted operators).

### 4.6 `join` on_condition

Line 225-246: accepts an arbitrary `on_condition` string for `JOIN ... ON`. Same issue as HAVING. **Delete or restructure.**

---

## 5. Standalone bulk nodes (`nodes/bulk_*.py`) — DELETE

### 5.1 `bulk_create.py` — 535 lines of parallel implementation

`nodes/bulk_create.py:391-446` `_build_insert_query`:

- Line 409: `escaped_value = value.replace("'", "''")`. The only defense. Defeated under PostgreSQL backslash-escape mode or with an attacker-controlled non-ASCII quote.
- Line 410-416: numeric values go in via `str(value)` with no escaping. An attacker-controlled int — for example from a tool output — that is actually a string `"1 OR 1=1"` becomes raw SQL.
- Line 420: `f"INSERT INTO {self.table_name} ({column_names}) VALUES {', '.join(value_rows)}"`. Column names come from `processed_data[0].keys()` at line 297. If a caller controls keys in the first record, they control the identifiers. No whitelist.
- Line 378-389: auto-injects `created_at = datetime.utcnow()` into each record. Violates the "never manually set timestamps" rule.
- Line 58: `self.table_name` is set from `kwargs.pop("table_name", None)` — an arbitrary string from the caller. Interpolated into SQL at line 420 and line 250. No quoting, no validation.
- Line 479: `if not row.get("email"): continue` — **hardcoded check for "email" field**. This is literally test-schema-specific code shipping in production. A model that doesn't have an `email` field is silently unaffected, but a model where `email` isn't required and the caller doesn't supply one gets rows silently dropped in the error-retry path. This is a stub / test-leak per zero-tolerance Rule 2.
- Line 529-533: on the connection-string fallback path, **a new `AsyncSQLDatabaseNode` is created per call**. This violates `rules/connection-pool.md` § 6 (no new pool per request).
- No transaction wrapping the batches. `_handle_batch_error` (line 463-500) silently continues on per-row exceptions. Partial failures leave the DB inconsistent.

### 5.2 `bulk_update.py` — 877 lines, worse

`nodes/bulk_update.py:344-360` (`_build_update_operators`):

- `$increment` / `$decrement`: `f"{field} = {field} + {operand}"`. Both `field` and `operand` interpolated as raw SQL.
- `$concat`: `f"{field} = {field} || '{operand}'"`. `operand` has NO escape. `'1' || 'x'); DROP TABLE users; --` is a direct injection.

`nodes/bulk_update.py:363-542` (`_execute_data_update`):

- Line 402-403: `update_dict["updated_at"] = "CURRENT_TIMESTAMP"`. Magic string.
- Line 412-413: `elif value == "CURRENT_TIMESTAMP": set_clauses.append(f"{field} = CURRENT_TIMESTAMP")`. If any caller passes a literal string `"CURRENT_TIMESTAMP"` for a text field, it gets spliced as raw SQL.
- Line 414-416: `escaped_value = value.replace("'", "''")`; `f"{field} = '{escaped_value}'"`. Same insufficient escaping as bulk_create.
- Line 420: `f"{field} = {value}"` — **any non-string non-None value goes in raw**. Int, float, bool, dict all become naked SQL tokens.
- Line 425: `f"id = {record_id}"`. `record_id` from the caller. **Raw interpolation.** If the `id` column is a string type (UUID, slug), the attacker controls the entire `WHERE` clause.
- Line 427: `f"tenant_id = '{tenant_id}'"`. Tenant escape is a tenant-isolation-bypass primitive. Subsystem 05 has more.
- Line 432-434: full query built by f-string. No parameterization.
- Line 439-445: **new `AsyncSQLDatabaseNode` instantiated inside the per-record loop.** Pool flood — N records produce N connections in the worst case. Combined with `validate_queries=False` at line 442, the SDK's safety net is disabled.
- No transaction. Each record is its own `async_run` call. A partial failure in row 500 of 1,000 leaves the first 499 updated and no way to recover.

Line 544-599 `_execute_ids_update`:

- Line 577: `escaped_value = value.replace("'", "''")`. Same defense.
- Line 582: `f"{field} = {value}"`. Same raw interpolation.
- Line 586: `f"{self.version_field} = {self.version_field} + 1"` — `version_field` is a configurable string (`version_control`). User-controllable in the init path.
- Line 592-594: `quoted_ids = [f"'{id_val}'" ... for id_val in ids]`. Quote-double defense; numeric IDs go in raw via `str(id_val)`.

### 5.3 `bulk_delete.py` — 586 lines, same pattern

- Line 265-277 `_estimate_affected_rows`: returns hardcoded fantasy values (`return 10000` for full-table, `return max(1, base_estimate // 2)`). This is **simulated data** per zero-tolerance Rule 2 — it pretends to be an estimator and is consumed downstream as a count. Either wire this to `EXPLAIN` or delete it.
- Line 299: `f"tenant_id = '{tenant_id}'"`.
- Line 307-312: string/int-sensitive id quoting with the same raw numeric interpolation vulnerability.
- Line 321: `f"SELECT * FROM {self.table_name} WHERE {where_clause}"` — SELECT-before-DELETE for `return_deleted`. `table_name` is caller-controlled.
- Line 368-384: soft-delete branch inlines `SET deleted_at = CURRENT_TIMESTAMP` (OK, literal) but `where_clause` itself was f-string constructed.
- Line 438-488 `_build_where_conditions`: same pattern as bulk_update's operator helper. Every MongoDB-style operator is implemented by f-string interpolation. `$gt`, `$gte`, `$lt`, `$lte` (lines 465-472) inline `operand` as a raw SQL token — perfect for `{"age": {"$gt": "18 OR 1=1"}}` injection.

### 5.4 Resolution for 5.1/5.2/5.3

**Delete `nodes/bulk_create.py`, `nodes/bulk_update.py`, `nodes/bulk_delete.py`, `nodes/bulk_upsert.py`, `nodes/bulk_create_pool.py`, `nodes/bulk_result_processor.py`.** The generated branches in `core/nodes.py:3350-3600` already exist and are the canonical implementation. The standalone files are:

1. A parallel unsafe implementation with multiple CRITICAL injection vectors.
2. Registered as nodes via `@register_node()` decorators, making them reachable even without the generator.
3. Referenced from `nodes/__init__.py` only transitively (not in the default `__all__`).
4. Covered by tests that MUST be migrated to the generated path before deletion.

### 5.5 Blanket `validate_queries=False` — 40+ sites

Grep: `validate_queries` returns 40+ call sites across `core/nodes.py`, `core/engine.py`, `features/bulk.py`, `utils/connection_adapter.py`, `nodes/bulk_update.py`, `nodes/bulk_create.py`, `migrations/`, `testing/`, and `migration/` (the dead one). Every single one disables the kailash core SDK's `AsyncSQLDatabaseNode` query validation layer.

`core/model_registry.py:240` is the canonical example: `"validate_queries": False` is baked into the helper that constructs cached `AsyncSQLDatabaseNode` instances. Every CRUD call inherits this.

What does `validate_queries=True` check? Core SDK's AsyncSQLDatabaseNode parses the query to verify it is a well-formed single statement (no `;` stacking), matches a dialect-specific whitelist of keywords, and blocks `DROP`, `TRUNCATE`, `ALTER`, etc. unless explicitly allowed. DataFlow disables this blanket — because DataFlow itself issues DDL for auto-migrations — but never re-enables it for DML. **That is the single biggest reason the CRITICAL-04 and CRITICAL-05 injections reach the database unchecked.**

The fix is:

1. `validate_queries=True` by default on all DML call sites (CRUD nodes, list, count, upsert, bulk).
2. `validate_queries=False` only on the DDL call sites, with a comment explaining why (schema migration needs ALTER).
3. Audit the SDK's validator to ensure it is strict enough; if not, tighten it.

This is a HIGH-severity discipline violation affecting the entire package.

---

## 6. Validation subsystems — two parallel directories

### 6.1 `validation/` (active)

`validation/__init__.py:21-60` exports:

- `field_validator`, `validate_model` (decorators and model validator)
- `ValidationResult`, `FieldValidationError`
- `email_validator`, `url_validator`, `uuid_validator`, `length_validator`, `range_validator`, `pattern_validator`, `phone_validator`, `one_of_validator`
- `StrictModeConfig`, `get_strict_mode_config`, `is_strict_mode_enabled`
- `apply_validation_dict`

Internal modules (`model_validator.py`, `parameter_validator.py`, `connection_validator.py`) all import from `dataflow.validation.validators` (internal). This is the real validation layer.

### 6.2 `validation/parameter_validator.py` — under-specified

`validate_update_node_parameters` at `validation/parameter_validator.py:215-327`:

1. Line 246-267: requires `filter` parameter. Good.
2. Line 270-291: requires `fields` parameter. Good.
3. Line 294-321: rejects `created_at`/`updated_at` in `fields`. Good.
4. **Does NOT reject unknown field names.** If `fields={"nonexistent_col": "x"}` is passed, validation passes and the SQL injection in § 3.2 fires.

Fix: add Rule 4 — reject any key in `fields` that is not in `model_fields` (or `auto_managed_fields`).

Same gap for `validate_create_node_parameters` at lines 61-207: Rule 3 (line 142-201) does type checking **only for fields in model_fields**, but does nothing about unknown keys. Rule 4 is needed: reject unknown keys.

Same gap for `validate_list_node_parameters` at line 335+: no operator whitelist for `filter` values, no upper bound on `limit`, no whitelist for `order_by` fields.

### 6.3 Strict mode is opt-in

`StrictModeConfig` is not enabled by default. `is_strict_mode_enabled()` returns `False` unless the caller explicitly turns it on. This means even the weak validation that exists is not running in the default flow. For a package that claims "enterprise-grade validation" in its `features/` directory, this is a HIGH.

### 6.4 `validators/` (plural) — DEAD

`validators/__init__.py` exports `StrictModeValidator` from `strict_mode_validator.py`. Grep across `src/`: **zero importers** outside the package-internal `__init__.py`. The class exists, the package exists, and nothing uses it. It duplicates the functionality in `validation/strict_mode.py`.

**Delete `validators/` entirely.** Move any unique test utilities into `validation/strict_mode.py` if needed.

---

## 7. Migration subsystems — two parallel directories

### 7.1 `migrations/` (active, 49 files)

Grep for `from dataflow.migrations`: imports from `core/engine.py`, `migrations/fk_aware_*.py`, `testing/dataflow_test_utils.py`. This is the wired migration subsystem.

Hub file: `migrations/auto_migration_system.py`:

- `auto_migrate()` at line 1637. See § 7.2.
- `_apply_migration()` — not audited in depth; inherits the lock-hold-then-DDL pattern.
- `_show_visual_confirmation` at line 1731 — bypassed by `auto_confirm=True`.
- Migration tracking table `dataflow_migrations` created at line 1950 / 1975.
- Migration lock table at line 2818.

Supporting files include `fk_aware_*.py` (four files, one called `fk_aware_system_demo.py` which is a **demo** in production code), `visual_migration_builder.py`, `rename_*.py` (three files), `safety_validation.py`, `impact_analysis_reporter.py`, etc. This is a **58-file migration orchestration system** with its own taxonomy of `risk`, `impact`, `rename coordination`, `batch executor`, and `performance tracker`. **Much of it is demo or exploratory code.**

### 7.2 Auto-migrate boot path — CRITICAL

`core/engine.py:5173-5225` `_trigger_sqlite_migration_system`:

```python
success, migrations = await self._migration_system.auto_migrate(
    target_schema=target_schema,
    dry_run=False,
    interactive=False,  # Non-interactive for SQLite
    auto_confirm=True,  # Auto-confirm for SQLite simplicity
)
```

The default `DataFlow()` construction, in the SQLite path, runs DDL against the database **immediately on first model registration** without any confirmation gate. And the failure handler at 5209-5212 says:

> `# Don't fail model registration - table will be created on-demand`

This means:

1. A production DataFlow app that boots against a database where the user lacks DDL privileges **silently continues** — the error is logged but not raised, and "the table will be created on-demand" — except the on-demand creation path has the same permission issue. The first real query fails. The app booted OK. The operator sees a 500 on the first request with no signal that the boot-time DDL failed.
2. There is **no append-only check on migration files**. `rules/schema-migration.md` Rule 4 says committed migration files must not be edited in place. DataFlow's auto-migrate generates SQL at runtime from the model and compares against the live schema; it has **no on-disk migration files** for CRUD-level operations. That is both a feature (no files to track) and a bug (no audit trail, no rollback, no SQL review).
3. There is **no dialect-matched migration test**. `rules/schema-migration.md` Rule 5: migrations MUST be tested against the production DB dialect. DataFlow's migration tests use a mix of SQLite and PostgreSQL; the existing integration suite in `tests/integration/migrations/` does cover both, but the auto-migrate boot sequence does NOT require the operator to point at a test dialect — it runs against whatever `config.database.url` is set to.

### 7.3 `migration/` (singular) — DEAD

`migration/__init__.py` imports `migration_executor`, `migration_generator`, `schema_comparison`. Grep across `src/`: **zero importers** of `dataflow.migration` (singular). The `from dataflow.migration.` searches return nothing. The directory is six files (data_validation_engine, migration_executor, migration_generator, orchestration_engine, schema_comparison, type_converter) with `validate_queries=False` hardcoded inside them (per § 5.5 grep).

This is a **dead parallel migration subsystem** shipped in production. Delete the entire `src/dataflow/migration/` directory.

### 7.4 `performance_data/migration_history.jsonl` — source tree telemetry

`migrations/performance_data/migration_history.jsonl` contains 44 JSONL records of historical migration runs. Per record:

- `timestamp`: 2025-08-03 onwards (dev machine timestamps)
- `success`: **`false` for every single entry**
- `error_message`: `"syntax error at or near \"WHERE\""`

The file is 44 entries of identical failed runs in the auto-migration system. They were journaled by `migrations/migration_performance_tracker.py:215` which default-paths to `Path(__file__).parent / "performance_data"`. That path is **the installed site-packages directory**. At runtime this would try to write into a potentially read-only location and either fail or pollute the source checkout.

The fact that these records exist in git at all is the signal: **someone ran the auto-migration in dev, it failed with the WHERE-clause bug, the failure was journaled to the source tree, and that state was committed.** This is:

1. A `rules/zero-tolerance.md` Rule 1 violation — there were 44 "syntax error at or near WHERE" failures and they were logged instead of fixed.
2. A `rules/git.md` violation — runtime telemetry committed to source.
3. Evidence of a real bug in `auto_migration_system` that was still generating broken SQL.
4. A design bug — writing to `__file__`-adjacent paths is never correct.

**Delete the file. Delete the default path. Route the tracker output to `$XDG_STATE_HOME/dataflow/` or a caller-provided directory. Then fix whatever was generating the broken WHERE clause.**

### 7.5 DROP COLUMN safety

`migrations/auto_migration_system.py:693-709`:

```python
sql_up = f"ALTER TABLE {table_name} ADD COLUMN {column_sql};"
sql_down = f"ALTER TABLE {table_name} DROP COLUMN {column.name};"
...
sql_up = f"ALTER TABLE {table_name} DROP COLUMN {column_name};"
```

DROP COLUMN is generated by the migration generator with no data-preservation plan. `migrations/column_removal_manager.py` implements backup strategies (`COLUMN_ONLY`, `TABLE_SNAPSHOT`, `CUSTOM_QUERY`, `NONE`) — but the auto-migrate generator at line 693 does NOT call `column_removal_manager`; it just emits `DROP COLUMN`. The backup subsystem exists and is **not wired** to the auto-migrate path.

This is a `rules/schema-migration.md` "no DROP without preserved-data plan" violation. The moment auto-migrate runs on a model where a column was removed, the column is gone with no backup.

SQLite branch at line 1343 is safer: it skips DROP COLUMN entirely with a log warning. PostgreSQL branch is dangerous.

### 7.6 Downgrade path

Migration operation defines `sql_down` at line 694 — `ALTER TABLE ... DROP COLUMN`. That downgrade REMOVES the column that the upgrade ADDED. Good. But for the `sql_up = DROP COLUMN` case at line 709, the generator at line 708-709 does NOT emit a recovery `sql_down` — the comment block above (not read in this audit, but inferred from the SQLite branch at 1384) says "cannot rollback DROP COLUMN". This means the DROP path is irreversible, violating `rules/schema-migration.md` Rule 3.

---

## 8. `classification/` — declared but unwired

### 8.1 Finding

`classification/__init__.py` exports `DataClassification`, `RetentionPolicy`, `MaskingStrategy`, `ClassificationPolicy`, `FieldClassification`, `classify`, `get_field_classification`. The `@classify` decorator attaches metadata to model fields. `get_field_classification(User, "email")` returns the attached metadata.

### 8.2 Reachability

Grep for `get_field_classification(`, `ClassificationPolicy(`, `MaskingStrategy.` outside of `classification/` itself:

- `src/dataflow/nodes/` — **zero hits**
- `src/dataflow/core/` — **zero hits**

`dataflow/__init__.py:72` re-exports the symbols. `dataflow/engine.py:13,458` imports `FieldClassification` — but only to pass through to users who write manual introspection code. **No CRUD node reads classification metadata. No read path applies masking. No retention policy is enforced.**

### 8.3 Implication

A user decorates `User.email` with `@classify("email", DataClassification.PII, RetentionPolicy.UNTIL_CONSENT_REVOKED, MaskingStrategy.REDACT)`, runs `UserReadNode`, and gets back the raw email. The classification is metadata-only. **Everything about the classification subsystem is a docstring lie** per mandate item 2.

### 8.4 Resolution

Either:

- **Wire it:** add `_apply_masking(row, model_name)` in the CRUD read path that iterates classifications and redacts/masks/hashes per policy. Same for retention (cascade deletes or row filters by `UNTIL_CONSENT_REVOKED` timestamps).
- **Delete it:** if the feature is not on the critical path, remove the subsystem and its exports. Keeping declared-but-unwired features is worse than not having them — users decorate their models, trust the promise, and leak PII.

Given the mandate is "perfect", wire it.

---

## 9. `optimization/` — test-support in production

### 9.1 Finding

`optimization/__init__.py` exports `WorkflowAnalyzer`, `SQLQueryOptimizer`, `SQLDialect`, `OptimizedQuery`, `QueryTemplate`, `IndexRecommendationEngine`, `IndexRecommendation`, `IndexAnalysisResult`, `IndexType`, `IndexPriority`, `QueryPlanAnalyzer`, `QueryPlanAnalysis`, `PlanNode`, `PerformanceBottleneck`, `PlanNodeType`, `BottleneckType`, `OptimizationOpportunity`, `PatternType`, `WorkflowNode`.

### 9.2 Reachability

Grep for consumers outside `optimization/`:

- `src/dataflow/testing/production_deployment_tester.py:31,92,93` — imports and instantiates.
- **Nothing else.**

The "query optimization" subsystem is consumed by one file, `production_deployment_tester.py`, which is itself in `testing/` — meaning optimization is test-support code shipped in production.

### 9.3 Resolution

Move `optimization/` into `testing/` or delete it. No CRUD node calls the optimizer. No query planner hints are issued. No index is auto-created from recommendations. The subsystem is dead weight.

---

## 10. `features/bulk.py` — third parallel bulk implementation

### 10.1 Finding

`features/bulk.py` is 1,100+ lines containing yet another bulk-insert/update/delete implementation. Line 384-390:

```python
result = await sql_node.async_run(
    query=query,
    params=params,
    fetch_mode="all",
    validate_queries=False,
    transaction_mode="auto",
)
```

This one is **parameterized** (`params=params`) and uses the cached SQL node. It is also the one used by the generated CRUD nodes' bulk branches in `core/nodes.py:3350-3600`. So `features/bulk.py` is the preferred parallel implementation... maybe. There are also direct calls from `core/nodes.py` that build SQL inline rather than calling into `features/bulk.py`.

### 10.2 Log-level downgrade

`features/bulk.py:375,392,420` use `logger.warning` for normal trace output:

- `:375` — "Executing batch N, query=..."
- `:392` — "SQL result=..."
- `:420` — "BULK_CREATE SUCCESS: ..."

These are INFO-or-DEBUG events. Per `rules/observability.md` Rule 3, `WARN` must mean "used a fallback or degraded path". Tagging successful operations as WARN poisons the log-triage protocol — every successful bulk insert now has a WARN that needs disposition. Downgrade to DEBUG.

### 10.3 Resolution

Consolidate `features/bulk.py`, `nodes/bulk_*.py`, and `core/nodes.py:3350-3600` into a single canonical implementation. Choose `features/bulk.py` as the winner (parameterized), delete the others, and inline `features/bulk.py` into `core/` next to the other generator code or keep it as the one import target for the generator branches.

---

## 11. Two transaction implementations, plus a fake

### 11.1 Real — `nodes/transaction_nodes.py`

Lines 118-298: `TransactionScopeNode`, `TransactionCommitNode`, `TransactionRollbackNode`, plus savepoint nodes. All use the real adapter via `_get_adapter_from_context(node)` at line 26-69, which pulls a `PostgreSQLAdapter` / `SQLiteAdapter` from the workflow context and calls the adapter's `transaction()` context manager, `commit()`, and `rollback()`. **This is correct.**

### 11.2 Real — `nodes/transaction_manager.py` (distributed)

Lines 51-57: delegates to kailash core SDK's `DistributedTransactionManagerNode`. This is a saga / 2PC wrapper. Correct pattern (framework-first).

### 11.3 Fake — `features/transactions.py`

**CRITICAL-06.** `features/transactions.py:11-78` `TransactionManager`:

- `transaction()` at line 18-58 creates a Python dict with `status="active"`, yields it to the caller, then sets `status="committed"` in the finally block.
- `rollback_all()` at line 64-77 mutates dict entries to `status="emergency_rollback"` and clears the dict.
- **No database connection. No SQL. No atomicity.**

And it is **wired into the public API** at `core/engine.py:453,2825`:

```python
self._transaction_manager = TransactionManager(self)  # line 453
@property
def transactions(self) -> TransactionManager:  # line 2825
    return self._transaction_manager
```

Every DataFlow instance exposes `db.transactions.transaction()` as a public context manager. The docstring at `features/transactions.py:22` says "Create a database transaction context" and "Transaction context with commit/rollback methods". **Both are lies.** A caller doing the blessed pattern:

```python
with db.transactions.transaction() as txn:
    await db.express.create("User", {"name": "Alice"})
    await db.express.create("Profile", {"user_id": ...})
    raise RuntimeError("halfway")  # user expects rollback
```

gets the `RuntimeError` propagated correctly, but **the first create was already committed**. The in-memory dict's `status` flips to `"rolled_back"` but the Postgres row is unaffected. This is data integrity by vibes.

### 11.4 Resolution

- Delete `features/transactions.py` entirely.
- `core/engine.py:453,2825` must either be removed (breaking change: `db.transactions` no longer exists) or rewritten to delegate to the real `TransactionScopeNode` by spinning up a one-node workflow.
- The correct ergonomic is `async with db.transaction() as txn:` which wraps the adapter's `transaction()` context manager directly. That's a 20-line rewrite that uses the existing `_get_cached_db_node(database_type).adapter` path.
- Until the fix ships, **warn loudly** — any caller of `db.transactions.transaction()` must immediately get a deprecation-that-raises at the top of the method. Anything less is consent to data corruption.

---

## 12. Query subsystem (`query/`)

### 12.1 Contents

- `query/sql_builder.py` (278 lines)
- `query/models.py` (184 lines)
- `query/aggregation.py` (229 lines)
- `query/errors.py` (60 lines)

Note: this is a separate subsystem from `database/query_builder.py` (§ 4). **Two parallel query builders.**

### 12.2 Which one runs?

`core/nodes.py:2599` imports `from ..database.query_builder import create_query_builder` (§ 4's builder) for the List operation. Grep for `from dataflow.query` / `from ..query`: hit count = modest. Let me skip a full audit of the parallel builder until phase 2 planning — it's the same-shape risk as the other duplication findings.

### 12.3 Resolution

Consolidate `dataflow/query/` and `dataflow/database/query_builder.py` into one. Pick the safer one (neither, per § 4.1-4.6). Rewrite the winner with:

- Field/table identifier whitelists against the model schema
- Parameterized `LIMIT`/`OFFSET`
- `MAX_LIMIT` (configurable via `DATAFLOW_MAX_LIST_LIMIT`, default `1000`)
- Escaped LIKE/REGEX wildcards by default
- `raise` on unknown operators (already correct) and unknown fields (currently silent)

---

## 13. Unknown field / silent parameter drop — formal finding

`.claude/rules/testing.md` warns: "UpdateNode is notorious for silently ignoring unknown parameter names."

Confirmed location: `core/nodes.py:2110-2126`, and:

- `core/nodes.py:2192` — `field_names = list(updates.keys())` without any filter against `self.model_fields`.
- `validation/parameter_validator.py:215-327` — strict-mode validator does not reject unknown keys in `fields`.
- `validation/parameter_validator.py:61-207` — same gap for CreateNode (strict-mode Rule 3 only type-checks known fields; unknown fields are silently ignored).

The fix is layered:

1. **Parameter validator**: add Rule 4 for both Create and Update: "unknown field names not in `model_fields` are rejected with `STRICT_PARAM_107`". Should be active by default (not strict-mode-only) because this is a correctness issue, not a style choice.
2. **Generated node body**: in the UpdateNode path at `core/nodes.py:2192`, before building SQL, intersect `updates.keys()` with `self.model_fields.keys()` and raise `NodeValidationError` on any leftover keys. The error message should include the unknown field name and the list of valid fields.
3. **Tests**: add a regression test for each model operation that verifies `fields={"nonexistent_col": "x"}` raises. Currently no test covers this path (grep for `nonexistent_col` / `unknown field` in `tests/` returns nothing).

---

## 14. Primary-key handling regression risk

`core/nodes.py:1338-1344`:

```python
for name in model_fields.keys():
    if name == "id":
        # Include ID if user provided it (Bug #3 fix allows users to use 'id')
        if "id" in kwargs:
            field_names.append(name)
        # Otherwise skip (will be auto-generated by database)
    elif name not in ["created_at", "updated_at"]:
        field_names.append(name)
```

This is the issue #42 / Bug #3 fix that allows an explicit `id` to survive the create path. The structure is **correct but fragile**: a single future rewrite that changes the iteration order or consolidates the `if/elif` risks reintroducing the silent drop. Add a regression test at `tests/integration/generated_nodes/test_create_id_passthrough.py` that:

1. Creates a User with explicit `id="u-12345"`
2. Reads back via UserReadNode
3. Asserts the returned id is `"u-12345"` exactly

Also verify the `model_fields.get("id", {}).get("type")` check at `nodes.py:2074-2089` does the right thing for UUID and string PKs. I did not exhaustively trace this.

---

## 15. Auto-managed timestamp enforcement

`CLAUDE.md` says: "Never manually set `created_at`/`updated_at` — DataFlow manages timestamps automatically (causes DF-104)."

Violations found:

- `nodes/bulk_create.py:378-389` manually sets `created_at` / `updated_at` to `datetime.utcnow()`. **HIGH.**
- `nodes/bulk_update.py:402-403` sets `update_dict["updated_at"] = "CURRENT_TIMESTAMP"`. **HIGH.**
- `nodes/bulk_update.py:559` sets `update_fields["updated_at"] = "CURRENT_TIMESTAMP"`. Same.
- `validation/parameter_validator.py:116-140`: correctly rejects manual timestamps in CreateNode (strict mode only).
- `validation/parameter_validator.py:294-321`: correctly rejects manual timestamps in UpdateNode fields (strict mode only).
- `core/nodes.py:1343, 1344` (create): correctly excludes timestamps from the field list during SQL generation. The adapter layer at `updated_at = CURRENT_TIMESTAMP` is appended at 2199-2261 (update) and implicit in the schema (create). **Correct.**

The pattern is: the generated nodes respect the rule; the standalone bulk nodes violate it. **Another argument for deleting the standalone bulk nodes.**

---

## 16. Pool leakage via per-row `AsyncSQLDatabaseNode`

`nodes/bulk_update.py:439-445` (inside the per-row loop):

```python
update_node = AsyncSQLDatabaseNode(
    connection_string=self.connection_string,
    database_type=self.database_type,
    validate_queries=False,
)
result = await update_node.async_run(query=query)
```

A new `AsyncSQLDatabaseNode` is constructed **per record**. 1,000-record bulk update = 1,000 ephemeral nodes, each with its own connection acquisition. `rules/connection-pool.md` § 6 requires application-level singleton pools. This is a pool flood at scale.

`nodes/bulk_create.py:529-533` has the same anti-pattern on the fallback path.

The generated bulk branches in `core/nodes.py:3350-3600` use `self.dataflow_instance._get_or_create_async_sql_node(database_type)` (see line 1484 for the CRUD create reference). This is the correct cached-node path. Another argument for deletion of standalone nodes.

---

## 17. Stubs, simulated data, magic strings — `rules/zero-tolerance.md` Rule 2 sweep

Discovered:

- `nodes/bulk_delete.py:265-277` `_estimate_affected_rows` — hardcoded fantasy estimator. Returns `10000` when no filter. STUB.
- `nodes/bulk_create.py:479` `if not row.get("email"):` — hardcoded test-schema assumption in the production error path. STUB.
- `nodes/bulk_update.py:403,412-413,559,574-575` — magic string `"CURRENT_TIMESTAMP"` used as a sentinel that triggers a SQL-splicing branch. NOT a stub per se but the behavior is undocumented and unsafe.
- `features/transactions.py:11-78` — entire class is a stub with `status="committed"`. LIE, not stub.
- `migrations/fk_aware_system_demo.py` — filename says "demo" in the production source tree. Need to verify if it is reachable from runtime code or if it is a dev scratchpad accidentally committed. If the latter, delete. If it self-registers or is imported by `fk_aware_*.py`, demote to `examples/`.
- `migrations/FK_AWARE_SYSTEM_SUMMARY.md` — a markdown documentation file in the source tree. Move to `docs/` or `packages/kailash-dataflow/docs/`.

---

## 18. Dead subsystems ready for deletion (summary)

Per the audit findings above, the following paths are candidates for deletion in the implementation phase:

| Path                                                               | Why                                 | LOC delta |
| ------------------------------------------------------------------ | ----------------------------------- | --------- |
| `src/dataflow/nodes/dynamic_update.py`                             | RCE, zero consumers                 | -223      |
| `src/dataflow/nodes/bulk_create.py`                                | SQL injection, parallel impl        | -535      |
| `src/dataflow/nodes/bulk_update.py`                                | SQL injection, parallel impl        | -877      |
| `src/dataflow/nodes/bulk_delete.py`                                | SQL injection, parallel impl        | -586      |
| `src/dataflow/nodes/bulk_create_pool.py`                           | parallel impl                       | -507      |
| `src/dataflow/nodes/bulk_upsert.py`                                | parallel impl                       | -577      |
| `src/dataflow/nodes/bulk_result_processor.py`                      | only consumed by deleted bulk nodes | -188      |
| `src/dataflow/features/transactions.py`                            | fake transaction                    | -78       |
| `src/dataflow/validators/`                                         | dead parallel validator             | -(~300)   |
| `src/dataflow/migration/`                                          | dead parallel migration             | -(~2000)  |
| `src/dataflow/migrations/performance_data/migration_history.jsonl` | telemetry committed to git          | -(~44 KB) |
| `src/dataflow/migrations/fk_aware_system_demo.py`                  | demo in production source           | -?        |
| `src/dataflow/migrations/FK_AWARE_SYSTEM_SUMMARY.md`               | docs in source tree                 | -?        |
| `src/dataflow/optimization/`                                       | test-support in production          | -(~1500)  |

Total: ~7,000+ lines of dead, unsafe, or mispositioned code to delete. The remaining delta is rewriting `db.transactions` to delegate to the real `TransactionScopeNode`, wiring `classification/` into the read path, enforcing the unknown-field rejection in the generator + validator, and fixing the LIMIT/OFFSET parameterization in `database/query_builder.py`.

---

## 19. Severity rollup

**CRITICAL:**

1. `nodes/dynamic_update.py` `exec()` on node parameter (§ 2) — RCE
2. `nodes/bulk_update.py` f-string SQL injection (§ 5.2)
3. `nodes/bulk_create.py` f-string SQL injection (§ 5.1)
4. `nodes/bulk_delete.py` f-string SQL injection (§ 5.3)
5. `core/nodes.py:2192-2248` UpdateNode identifier injection via `fields` keys (§ 3.2)
6. `database/query_builder.py:311-313` LIMIT/OFFSET raw interpolation (§ 4.1)
7. `database/query_builder.py:441-453` identifier non-escaping (§ 4.2)
8. `features/transactions.py` fake TransactionManager exposed as `db.transactions` (§ 11.3)
9. `migrations/auto_migration_system.py` + `core/engine.py:5191-5196` auto-confirm DDL on boot with swallowed failures (§ 7.2)
10. `migrations/` DROP COLUMN without data preservation (§ 7.5)
11. `nodes/bulk_update.py:403` magic-string `"CURRENT_TIMESTAMP"` raw SQL splice

**HIGH:**

1. Silent parameter drop in UpdateNode fallback path (§ 3.2, § 13)
2. `validate_queries=False` blanket on 40+ DML call sites (§ 5.5)
3. `classification/` subsystem declared but unwired — PII promise unkept (§ 8)
4. `optimization/` subsystem dead (§ 9)
5. `migration/` (singular) dead parallel subsystem (§ 7.3)
6. `validators/` (plural) dead parallel subsystem (§ 6.4)
7. No upper cap on `limit`/`offset` (§ 3.3)
8. LIKE/REGEX wildcard not escaped (§ 4.3)
9. `join`/`having` accepts raw SQL strings (§ 4.5, § 4.6)
10. `migrations/performance_data/migration_history.jsonl` committed telemetry + broken WHERE SQL in history (§ 7.4)
11. `features/bulk.py` parallel bulk implementation (§ 10)
12. Three parallel transaction implementations (§ 11)
13. Two parallel query builders (`query/` vs `database/query_builder.py`) (§ 12)
14. Pool flood: `AsyncSQLDatabaseNode` per record in standalone bulk nodes (§ 16)
15. Timestamp auto-management violated in standalone bulk nodes (§ 15)
16. `features/bulk.py:375,392,420` log-level downgrade (§ 10.2)
17. Strict mode is opt-in — default validation is a stub (§ 6.3)

**MEDIUM:**

1. Generated CRUD class body is 3,771 lines in a single closure — hostile to review (§ 3)
2. `core/nodes.py:2581` mutates caller's `filter_dict` in place (soft-delete auto-filter) (§ 3.3)
3. `core/nodes.py:2636` default `ORDER BY id DESC` on every list — O(n log n) on unindexed tables (§ 3.3)
4. PostgreSQL `$N` placeholder numbering races with tenant-isolation rewrite at line 2276 (§ 3.2)
5. Failed-migration fallback at `engine.py:5209-5212` swallows DDL errors (§ 7.2)
6. `nodes/bulk_create.py:479` hardcoded `"email"` assumption (§ 5.1)
7. `nodes/bulk_delete.py:265-277` fantasy estimator (§ 17)
8. `migrations/fk_aware_system_demo.py` in production source tree (§ 17)
9. `migrations/FK_AWARE_SYSTEM_SUMMARY.md` docs in source tree (§ 17)

**LOW:**

1. Deprecated parameters `conditions`/`updates` still accepted — remove in v0.8.0 per the existing warnings (core/nodes.py:1993-2012)
2. `is_empty()` helper at `core/nodes.py:1965-1974` defined inline inside the operation dispatch; should be a module-level helper
3. Line 2034-2044 parses `updates_dict` via `ast.literal_eval` as a fallback — magic string parsing is fragile, should require callers to pass actual dicts
4. `nodes/__init__.py:31-33` catches ImportError as "kailash 3.x removed Python Node base class" — a try/except import that silently disables half the package. Per `rules/dependencies.md` "no silent ImportError degradation", this is BLOCKED. Fail loudly or declare an optional extra.

---

## 20. Cross-SDK check (kailash-rs)

Per `rules/cross-sdk-inspection.md`, every finding in a BUILD repo triggers an inspection of the other BUILD repo. The following cross-SDK tickets should be filed against `esperie-enterprise/kailash-rs` `crates/kailash-dataflow`:

| Python finding                                | Rust cross-check                                                   |
| --------------------------------------------- | ------------------------------------------------------------------ |
| CRITICAL-01 DynamicUpdateNode RCE             | Does kailash-rs have an equivalent dynamic code-exec node? Delete. |
| CRITICAL-02/03/04 bulk SQL injection          | Does kailash-rs build SQL by `format!()` on user fields? Audit.    |
| CRITICAL-05 LIMIT/OFFSET raw interpolation    | Is `sqlx` being used with parameterized LIMIT? Verify.             |
| CRITICAL-06 fake TransactionManager           | Is there a `transactions` API that doesn't call `begin()`?         |
| CRITICAL-08 auto-migrate without confirmation | Is the Rust auto-migrate confirming?                               |
| HIGH `classification/` unwired                | Does Rust have `@classify` with matching semantics and wiring?     |
| HIGH `validate_queries=False` everywhere      | Does sqlx-level prepared-statement validation run on every call?   |

File each as a separate issue with the `cross-sdk` label and link to this audit.

---

## 21. Framework-first compliance

Per `rules/framework-first.md`, raw SQL is BLOCKED when DataFlow nodes exist. Inside DataFlow itself, the equivalent rule is: the adapter layer owns SQL; the node generator and query builder consume the adapter. Violations:

- Every `nodes/bulk_*.py` file builds SQL by f-string and passes the string to `AsyncSQLDatabaseNode`. They bypass the adapter's parameter binding.
- `migrations/auto_migration_system.py:693-709` builds ALTER statements by f-string. Acceptable for DDL where parameter binding is not available, but the table/column names should be identifier-quoted via an adapter helper.

Inline SQL inside DataFlow is OK **if and only if** it is parameterized against the adapter. Anywhere a `f"..."` contains user-controlled identifiers or values is a failure.

---

## 22. Next actions

1. **Delete** the files in § 18. Scope: ~7,000 LOC. Migrate any tests that referenced the deleted paths to the generated-node path.
2. **Add unknown-field rejection** to `core/nodes.py:2192` (UpdateNode) and `validation/parameter_validator.py` (default validator). Add regression test.
3. **Cap limit/offset** to a configurable max in `core/nodes.py:2513-2515` and in `database/query_builder.py:215-223`. Parameterize the SQL emission at `query_builder.py:311-313`.
4. **Escape LIKE/REGEX** metacharacters by default in `database/query_builder.py:161-177`.
5. **Fix identifier quoting** at `database/query_builder.py:441-453` to escape embedded quote characters, or whitelist identifiers at the caller.
6. **Rewrite `db.transactions`** in `core/engine.py:2825` to delegate to `TransactionScopeNode`. Delete `features/transactions.py`.
7. **Wire classification** into the generated ReadNode/ListNode path so `@classify`-decorated fields are masked on read per `MaskingStrategy`.
8. **Add `validate_queries=True`** as the default for all DML call sites; keep `False` only in `core/engine.py` DDL paths with justifying comments.
9. **Gate auto-migrate** on a `confirm_migrations: bool = False` constructor parameter. Default is "emit the planned SQL, log at WARN, and raise unless the caller opted in". Production boot that silently runs DDL is unacceptable.
10. **Preserve data on DROP COLUMN** by wiring `column_removal_manager.py` into `auto_migration_system.py:708-709`.
11. **Move `migrations/performance_data/`** out of the source tree. Delete the committed `migration_history.jsonl`. Fix the WHERE-clause bug that generated those 44 failed runs.
12. **Log-level discipline** in `features/bulk.py:375,392,420` — WARN → DEBUG.
13. **Delete `migration/` (singular)** entirely.
14. **Delete `validators/` (plural)** entirely.
15. **Move `optimization/` to `testing/`** or delete.
16. **Consolidate** `query/` and `database/query_builder.py` into one query builder module.
17. **Cross-SDK file** all CRITICAL + HIGH findings against kailash-rs per § 20.

Sequencing goes into `02-plans/01-master-fix-plan.md`. The deletions are parallel-safe (dead code); the rewrites have ordering constraints (validator rule must land before generator rule; auto-migrate gate must land before DROP COLUMN preservation; `db.transactions` rewrite must land with a deprecation shim to avoid breaking existing callers mid-flight).

---

## 23. Test coverage gaps

Per `rules/testing.md` § State Persistence Verification, every CreateNode/UpdateNode test must (1) issue the API call, (2) verify the API returned 200, AND (3) read back the row to verify the write landed. From the directory listing:

- `tests/integration/bulk_operations/` has files for `bulk_create_node`, `bulk_update_node`, `bulk_delete_node`. Did not deep-audit.
- `tests/integration/core_engine/` has `test_delete_node_validation.py`.
- **No `tests/integration/generated_nodes/` directory exists.** The generated CreateNode / UpdateNode / ListNode path (`core/nodes.py:279-3700`) is not covered by a dedicated test suite. Coverage comes indirectly through bulk tests and workflow-level tests.

Gap list:

- No test for "CreateNode with explicit `id` survives" (issue #42 regression).
- No test for "UpdateNode with unknown field name raises" (the CRITICAL-04 regression I'm asking to be fixed).
- No test for "ListNode with `limit=10**9` is capped".
- No test for "ListNode with `order_by=['name DESC; DROP TABLE users--']` raises".
- No test for "LIKE wildcard is escaped by default".
- No test for "REGEX pattern length is capped".
- No test for "auto-migrate with `auto_confirm=False` prompts".
- No test for "DROP COLUMN preserves data to backup table".
- No test for "`db.transactions` actually commits to PostgreSQL" (this is how you discover `features/transactions.py` is a lie — you can't, because there's no such test).

These tests **must be added as part of the fix**. Their absence is itself a HIGH finding — without them, any future rewrite silently reintroduces the same bugs.

---

## 24. Summary

DataFlow's CRUD, query, bulk, migration, and validation subsystems contain **11 CRITICAL issues** (primarily SQL injection, RCE, fake transactions, and auto-DDL-without-confirmation), **17 HIGH issues** (disabled validation, dead code, unwired features), and **~15 MEDIUM/LOW issues**. Approximately 7,000 lines of code are candidates for outright deletion as dead, unsafe, or mispositioned parallel implementations. The remaining fixes are surgical: identifier whitelisting, parameterized LIMIT/OFFSET, classification wiring, unknown-field rejection, real `db.transactions`, gated auto-migrate, DROP COLUMN preservation.

The fake `TransactionManager` and the `DynamicUpdateNode` RCE are the two immediate-blockers for any production claim. Everything else is structural debt that "DataFlow MUST be perfect" requires closing in this sprint.
