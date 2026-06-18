# 0001 — DISCOVERY: #1249 cross-tenant leak verified live; fail-closed architecture

**Date:** 2026-06-03
**Issue:** #1249 (CRITICAL) — DataFlow multi-tenant `express` provides NO isolation.
**Status:** Analysis complete, verified by live repro. Ready for /implement.

## Verified diagnosis (live, on current source @ dataflow 2.10.3)

Reproduced via `/tmp/repro_1249.py` and `/tmp/repro_1249_leak.py`. All claims
re-read against current code by the orchestrator (file:line citations below).

### Current behavior (no patch): accidental fail-close

`express_sync.create` under a bound tenant **raises** `RuntimeError: Tenant
isolation failed … Malformed SQL: INSERT statement missing table name`. No row
is written → no leak yet, but multi-tenant create is non-functional.

### With naive validator fix (no-op the SQL-syntax validator): SILENT LEAK

Both rows persist with `tenant_id = None`; acme reads `[10, 99]` (sees globex's
row). **Cross-tenant leak proven.** This is why the validator fix MUST NOT ship
alone.

## Four compounding defects (all verified)

1. **Validator `\w+` rejects quoted identifiers** —
   `tenancy/interceptor.py:987` (INSERT), `:994` (UPDATE), `:1001` (DELETE).
   `INSERT\s+INTO\s+\w+` cannot match `INSERT INTO "feats" …`. Currently
   fail-closes the INSERT path (loud RuntimeError).
2. **Write stores `tenant_id = NULL`** — `_inject_insert_conditions`
   (`interceptor.py:744`) regex `INSERT\s+INTO\s+\w+\s*\(...\)` (line 755) does
   not match quoted identifiers, so the tenant column/value is never appended.
   Verified: raw rows `(e1,10,None) (e1,99,None)`.
3. **Read returns all rows cross-tenant** — `inject_tenant_conditions`
   (`interceptor.py:199`) calls `is_tenant_table` (`:269`) which compares the
   parsed (quoted) table name against the unquoted `tenant_tables=[table]`
   passed from `nodes.py:758`. Mismatch → `tenant_tables_in_query` empty (line 223) → **returns the query UNCHANGED, no WHERE filter, no error** (the
   silent-leak hole). Verified: acme `list` returns `[10, 99]`.
4. **`tenant_isolation_strategy` silently ignored** — stored at
   `config.py:571` (default `"schema"`), but `_apply_tenant_isolation`
   (`nodes.py:712`) never consults it (always row-injection) and the
   constructor drops it as an unknown param (DF-CFG-001). `"schema"` is a no-op
   on SQLite (no schemas).

## Call-graph (single enforcement point)

`express.create/list/...` → `_create_node` → SQL node `async_run` →
`nodes.py::_apply_tenant_isolation` (`:712`, called from INSERT `:1867`, SELECT
`:2263`, UPDATE `:2675`, DELETE `:2857`, upsert `:3091`, …) → constructs
`QueryInterceptor(tenant_id, tenant_tables=[table], tenant_column="tenant_id")`
(`:756`) → `inject_tenant_conditions`. The interceptor IS the intended single
enforcement point. Express's `_resolve_tenant_id` (`express.py:1721`) is
correct but only partitions the **cache key** — not the SQL.

## Root cause

Regex-based identifier matching in the interceptor is broken for quoted
identifiers across validation (`\w+`), table-matching (`is_tenant_table`), and
injection (`\w+`). The same normalization gap manifests three ways, plus a
silent-pass-through fail-open on the SELECT path.

## Architecture (fail-closed; the open question is resolved to "BOTH")

The session notes left "fail-closed-at-startup vs wire row-isolation
everywhere" open. Resolution: **both**, layered. Refusing multi-tenant SQLite
entirely is strictly worse (breaks the documented feature). Required:

1. **Identifier normalization** — normalize quoted/bracketed identifiers
   (`"feats"`↔`feats`, `` `feats` ``, `[feats]`) in `parse_query` /
   `is_tenant_table` / the INSERT/UPDATE/DELETE injection regexes so matching
   and injection work regardless of dialect quoting. Single root-cause fix for
   defects 1–3.
2. **Write sets tenant_id** — INSERT injection appends the tenant column+value
   for quoted-identifier INSERTs (verify raw `tenant_id` ≠ NULL).
3. **Read/Update/Delete filter** — `WHERE tenant_id = ?` actually injected
   (verify cross-tenant read returns only own rows).
4. **Fail-closed guard** — when the interceptor is constructed with an explicit
   `tenant_tables=[table]` (caller knows it is a tenant table) and the parse
   fails to match / cannot inject, it MUST raise `TenantIsolationError`, NOT
   return the query unchanged (close the line-223 silent-leak hole). Per
   `tenant-isolation.md` MUST-2 + `zero-tolerance.md` Rule 3.
5. **Strategy honored or rejected at startup** — `tenant_isolation_strategy`
   either drives behavior or, on a backend/strategy that cannot isolate, fails
   closed at startup with a clear error. Fix DF-CFG-001 (no silent drop).
6. **Tier 2/3 regression** — two-tenant create + cross-tenant read-back asserts
   strict isolation, on BOTH SQLite and Postgres; INSERT/UPDATE/DELETE paths;
   quoted-identifier validator regression; `tenant_id=NULL`-never assertion.

## Cross-SDK (per cross-sdk-inspection.md)

The kailash-rs tenant-injection path is structurally different (the issue notes
it is "likely unaffected"). A parity glance is required before close, but the
fix here is Python-DataFlow-internal SQL generation.

## Receipts

- Live repro (fail-close): `/tmp/repro_1249.py` — INSERT raises.
- Live repro (leak): `/tmp/repro_1249_leak.py` — `tenant_id=None`, acme reads `[10,99]`.
