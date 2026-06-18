# 0001 — DISCOVERY: #1252 bulk tenant-isolation root cause

**Date:** 2026-06-03
**Issue:** #1252 (HIGH) — multi-tenant `bulk_create`/`bulk_update`/`bulk_upsert`/`upsert`
provide no tenant isolation. Follow-up to #1249 (single-record, shipped 2.11.0).

## Root cause: bulk subsystem reads the WRONG tenant source

The bulk operations delegate from the node (`nodes.py:3777`) to a separate
subsystem `self.dataflow.bulk` = `BulkOperations` (`features/bulk.py`), which
builds its own SQL and does NOT route through `_apply_tenant_isolation` /
`QueryInterceptor`. The subsystem HAS inline tenant handling, but reads the
wrong source:

- `tenant_context.switch("acme")` sets the `_current_tenant` **ContextVar**
  (`core/tenant_context.py:220`); `get_current_tenant_id()` reads it (`:404`).
  This is the source the single-record path + `_apply_tenant_isolation` use.
- `bulk.py` reads `self.dataflow._tenant_context.get("tenant_id")` — a SEPARATE
  legacy dict (`engine.py:480` `self._tenant_context = {} if multi_tenant`),
  only populated by the unused `set_tenant_context()` API (`engine.py:2825`).
  Under `switch()` that dict stays empty `{}` → `tenant_id` never set → NULL.

Mechanical confirmation: `grep -c _tenant_context bulk.py` = 4;
`grep -c get_current_tenant_id bulk.py` = 0 (never imported).

## Full defect scope (all four bulk ops, all in features/bulk.py)

1. **bulk_create** (`:247`, tenant block `:278-282`) — sets `record["tenant_id"]`
   from the stale `_tenant_context` dict → NULL writes under `switch()`.
2. **bulk_upsert** (`:963`, tenant block `:1025-1029`) — same stale-dict read;
   plus the `ON CONFLICT (id)` target (`:1204/:1213`) errors under multi-tenant
   ("ON CONFLICT clause does not match") — needs tenant_id composed correctly.
3. **bulk_update** (`:447`) — builds `UPDATE {table} {set} {where}` (`:562/:728`)
   with NO `tenant_id` in the WHERE → latent cross-tenant write (a filter that
   matches another tenant's rows would update them).
4. **bulk_delete** (`:801`) — builds `DELETE FROM {table} {where}` (`:896`) with
   NO `tenant_id` in the WHERE → latent cross-tenant delete.

Verified live (#1252 repro): bulk_create stores `tenant_id=None` (rows invisible
to all tenants); bulk_update no-op; upsert raises ON CONFLICT. NOT a cross-tenant
disclosure (NULL rows invisible; update/delete didn't leak in the empty-filter
test) — but broken + fail-open.

## Architecture (fix in features/bulk.py)

The bulk subsystem keeps its own inline injection (it already has the shape);
the fix corrects the SOURCE + adds the missing scoping + fails closed. Do NOT
re-route bulk through the interceptor (its regex injection doesn't handle
multi-row VALUES / ON CONFLICT; that is a larger refactor, out of scope).

1. Import + use `get_current_tenant_id()` for the tenant source in ALL four ops
   (replace all 4 `self.dataflow._tenant_context.get(...)` reads).
2. **create/upsert**: set `record["tenant_id"]` from the contextvar.
3. **update/delete**: inject `AND tenant_id = ?` (bound param) into the WHERE for
   tenant tables.
4. **upsert ON CONFLICT**: compose so the conflict target works under
   multi-tenant (tenant_id present in columns; conflict on the PK still valid).
5. **Fail closed** (per `tenant-isolation.md` MUST-2 + `zero-tolerance.md` Rule 3
   - the #1249 `_apply_tenant_isolation` precedent): a bulk op on a tenant table
     under `multi_tenant=True` with NO bound tenant MUST raise, not write/scope NULL.
6. Tenant value MUST be a bound parameter (`security.md`).

## Tests

Tier-2 cross-tenant bulk isolation (SQLite + Postgres-marked): two-tenant
bulk_create + cross-read; bulk_update/bulk_delete cannot touch another tenant's
rows; bulk_upsert round-trips under a tenant; fail-closed no-tenant bulk op
raises. Reuse `/tmp/rt_bulk.py` + `/tmp/rt_bulk_mutate.py` as the live loop.

## Receipts

- `engine.py:480` (`_tenant_context = {}`), `:2825` (`set_tenant_context`).
- `tenant_context.py:220` (contextvar set by switch), `:404` (`get_current_tenant_id`).
- `bulk.py:278-282`, `:1025-1029` (stale-dict reads); `:562/:728/:896` (WHERE, no tenant).
