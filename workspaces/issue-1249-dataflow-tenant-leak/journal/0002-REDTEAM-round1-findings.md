# 0002 — REDTEAM Round 1: #1249 tenant-isolation fix

**Date:** 2026-06-03
**Method:** Sub-agent fan-out (3 reviewers + a 7-lens workflow) all died on a
persistent global rate-limit (0 tokens). Round 1 was therefore run by the
orchestrator directly with live attack scripts (`/tmp/rt_*.py`) — the most
rigorous channel (ground-truth behavior, no delegation).

## Verdict on the single-record path: CONVERGED (clean)

Verified SECURE via live cross-tenant attack scripts (all PASS):

- Read isolation (list / read-by-PK→None / filtered list).
- Write isolation: cross-tenant UPDATE and DELETE by PK are no-ops (globex
  unchanged when acme targets globex's PK).
- INSERT persists correct non-NULL `tenant_id`.
- Injection: a malicious `tenant_id` value (`x' OR '1'='1`) is bound as a
  parameter, isolation holds, no SQL injection.
- Strategy fail-closed at startup: `schema`/`database`/invalid → typed raise;
  `row` → ok. DF-CFG-001 fixed (param accepted, not silently dropped).
- Interceptor fail-closed guards: declared-tenant-table-no-match → raise;
  no-op injection → raise (interceptor.py:275-297, 336-342). Reviewed, sound.

## Finding A (HIGH) — FIXED this session

**No-tenant write fail-OPEN.** Under `multi_tenant=True` with NO bound tenant,
`nodes.py::_apply_tenant_isolation` returned the query unchanged (the original
`if not tenant_id: return query, params` at :737), so an INSERT persisted a
`tenant_id=NULL` row _before_ the API-layer `TenantRequiredError` fired. Not a
cross-tenant disclosure (NULL invisible to filtered reads) but a latent
fail-open violating tenant-isolation.md MUST-2 + zero-tolerance.md Rule 3.

**Fix:** reordered `_apply_tenant_isolation` so DDL-bypass + non-tenant-model
checks run first, then a tenant-isolated model with no bound tenant under
multi_tenant raises (RuntimeError "no tenant is bound"). DDL/auto-migrate still
bypass (verified). Regression: `test_express_multi_tenant_write_without_bound_tenant_fails_closed`
(end-to-end: raises + asserts zero NULL-tenant rows) + updated wiring test
`test_no_tenant_context_fails_closed_under_multi_tenant` + new
`test_ddl_passes_through_without_tenant_context`. 19 #1249 tests + 91 tenancy
tests pass.

## Finding B (HIGH, SEPARATE WORKSTREAM) — surfaced, NOT fixed

**Bulk/upsert paths are not tenant-isolated.** `bulk_create` silently writes
`tenant_id=NULL` rows under a bound tenant (data then invisible to every
tenant: `acme: []`, `globex: []`, `count: 0`). `bulk_update` mutates nothing
(safe but broken). `upsert` raises `ON CONFLICT clause does not match`.

Root cause: the bulk INSERT generation has NO `_apply_tenant_isolation` call
site — every enforcement-point call is single-record (create:1894, list:2290,
update:2702, delete:2884, upsert:3118/3452/3495, count:3686). The bulk path is
a MISSING enforcement-point class (orphan-detection.md).

**NOT a cross-tenant disclosure** (NULL rows invisible; bulk_update doesn't
leak; upsert raises) — but broken + fail-open. Fixing requires multi-row INSERT
injection + ON CONFLICT composition with tenant_id across bulk_create /
bulk_update / bulk_upsert / upsert — a distinct, larger shard (>1 session,
different SQL shapes). Per autonomous-execution.md Rule 4 bound, this exceeds
the #1249 shard → its own issue/workstream. #1249's acceptance criteria
(single-record express CRUD) are fully met.

## Receipts

- `/tmp/rt_isolation.py` (all ops isolated), `/tmp/rt_failclosed.py` (strategy +
  no-tenant + injection), `/tmp/rt_bulk.py` + `/tmp/rt_bulk_mutate.py` (the B
  gap). Suite: 91 passed / 9 skipped / 10 deselected (Postgres-infra).
- Diff: config.py +11, engine.py +100, nodes.py +41, interceptor.py +383,
  wiring test +39; 2 new regression test files. No commits (HEAD 02d7bbacf).
