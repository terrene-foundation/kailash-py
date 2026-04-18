# Orphan Sweep — Round 1

**Scope:** kailash-py — full facade / orphan audit
**Protocol:** `rules/orphan-detection.md` + `rules/facade-manager-detection.md`
**Date:** 2026-04-18

## Summary

| Severity | Finding                                                       | Disposition                                          |
| -------- | ------------------------------------------------------------- | ---------------------------------------------------- |
| HIGH     | `BulkUpsertNode` pool-path unreachable (Issue #494 confirmed) | Delete pool branch OR implement                      |
| HIGH     | `DataFlow._tenant_trust_manager` orphan — set, never read     | Wire OR delete                                       |
| MEDIUM   | Phase 5.11 wiring tests are monolithic, not per-facade        | Split per `rules/facade-manager-detection.md` Rule 2 |
| LOW      | `BulkOperations` only exercised by downstream tests (ok)      | No action — tests are externally observable          |

Collect-only: ALL four trees clean (5839 + 2044 + 11189 + 15959 = 35,031 tests). Zero ModuleNotFoundError. Recent deletions (commits d3e7e0ef, 5edc941f, e550949c) already swept.

---

## HIGH-1 — BulkUpsertNode pool-path orphan (Issue #494)

**Claim under test:** session notes state `DataFlowConnectionManager.execute()` does not implement `operation='execute'`, so the pool branch in `BulkUpsertNode._execute_query` falls back silently.

**File:** `packages/kailash-dataflow/src/dataflow/nodes/bulk_upsert.py:618-630`

**Code under test:**

```python
if use_pooled_connection and self.connection_pool_id and self._pool_manager:
    try:
        return await self._pool_manager.execute(
            operation="execute", query=query, params=params
        )
    except Exception as e:
        logging.warning(
            f"Failed to execute via pool: {e}, falling back to direct connection"
        )
```

**Call site inspected:** `packages/kailash-dataflow/src/dataflow/nodes/workflow_connection_manager.py:156-171`

```python
def execute(self, **kwargs) -> Dict[str, Any]:
    operation = kwargs.get("operation", "initialize")
    if operation == "initialize":     return self._initialize_pool(**kwargs)
    elif operation == "get_connection":   return self._get_connection()
    elif operation == "release_connection": return self._release_connection(...)
    elif operation == "stats":            return self._get_pool_stats()
    elif operation == "configure_smart_nodes": return self._configure_smart_nodes(**kwargs)
    else:
        raise ValueError(f"Unknown operation: {operation}")
```

**Evidence:** `operation="execute"` is NOT in the allowlist. Every pool-path call raises `ValueError`, which is caught by bare `except Exception` at bulk_upsert.py:624, logged at WARN, and silently falls through to the direct AsyncSQLDatabaseNode path.

**Why HIGH:** This is the Phase 5.11 orphan shape exactly — a facade (`_pool_manager.execute(operation="execute", ...)`) is invoked on a production hot path (every bulk upsert), the call always raises, and the resulting fallback masks it. Operators believe the pool is wired; it isn't. `rules/zero-tolerance.md` Rule 3a (silent fallback) + `rules/dataflow-pool.md` Rule 3 (no deceptive configuration).

**Disposition — two acceptable fixes (both MUST ship with a regression test):**

1. **Delete the pool branch** — remove lines 618-630 and the `use_pooled_connection` / `_pool_manager` plumbing. Bulk upsert runs only via AsyncSQLDatabaseNode. Simplest, and matches the sibling `BulkCreateNode` which does not have a pool branch.
2. **Implement it** — add `elif operation == "execute"` in `DataFlowConnectionManager.execute()` that acquires a pooled connection and runs the query. Required if any downstream feature actually depends on pool reuse.

**BLOCKED disposition:** leaving the branch with a `try/except Exception` fallback. That is the exact bug `rules/zero-tolerance.md` Rule 3 forbids — catch → log → continue with no plan to fix.

**Regression test:** MUST reproduce via `db.bulk.bulk_upsert(...)` with a configured `DataFlowConnectionManager` and assert either (a) pool path succeeds and direct path is not touched, or (b) pool-path feature flag is absent after the delete.

---

## HIGH-2 — `DataFlow._tenant_trust_manager` orphan

**File:** `packages/kailash-dataflow/src/dataflow/core/engine.py:627` (declared) + `:664` (assigned)

**Zero-call-site evidence:**

```bash
# Set-sites:
rg 'self\._tenant_trust_manager' packages/
  packages/kailash-dataflow/src/dataflow/core/engine.py:627  (declaration)
  packages/kailash-dataflow/src/dataflow/core/engine.py:664  (assignment)

# Read-sites (expected: >= 1 call into the manager's methods from the framework hot path):
rg 'self\._tenant_trust_manager\.' packages/
  (empty — zero results)

rg '_tenant_trust_manager\.' packages/
  (empty — zero results)

rg 'tenant_trust_manager\.' packages/ src/
  (empty — no method calls anywhere)
```

**Documented-but-not-wired:** `specs/dataflow-core.md:373` lists this as "Multi-tenant trust isolation (enabled when both `multi_tenant=True` and trust mode is not `disabled`)". Downstream readers of the spec believe tenant trust isolation is enforced on the hot path. It isn't.

**Tier 2 wiring-test evidence:** `packages/kailash-dataflow/tests/regression/test_phase_5_11_trust_wiring.py:263` only checks `assert db._tenant_trust_manager is not None` — instantiation, not invocation. No test triggers a code path that calls a method on `_tenant_trust_manager`, because no such code path exists.

**Why HIGH:** Identical shape to the Phase 5.11 orphan (`TrustAwareQueryExecutor` was facade-ed, documented, and never invoked) — the fix for `_trust_executor` did NOT propagate to `_tenant_trust_manager`. `rules/orphan-detection.md` Rule 1 (production call site within 5 commits) + `rules/facade-manager-detection.md` Rule 1 (Tier 2 test asserts externally-observable effect).

**Disposition — wire OR delete:**

- **Wire:** identify the invariant this manager enforces (multi-tenant + trust audit gate on every express.list / express.read) and add the call site in `packages/kailash-dataflow/src/dataflow/features/express.py` next to the existing `self._db._trust_executor.*` calls. Port the wiring test to behavioral (external effect on an audit row, or a cross-tenant query rejection).
- **Delete:** remove lines 627 + 664, remove the import in `engine.py`, update `specs/dataflow-core.md:373`. Simplest if the manager was speculative.

**BLOCKED disposition:** leaving the assign-site with a comment "reserved for future wiring". That is `rules/zero-tolerance.md` Rule 2 (no stubs in production code) — the class is instantiated, imported by downstream consumers, and documented as live.

---

## Phase 5.11 fix reverification — `_trust_executor` + `_audit_store`

**Claim under test:** session notes assert Phase 5.11 wired `TrustAwareQueryExecutor` and `DataFlowAuditStore`.

**Evidence it IS wired:**

```bash
rg 'self\._db\._trust_executor' packages/kailash-dataflow/src/dataflow/features/express.py
  :291  return getattr(self._db, "_trust_executor", None) is not None
  :308  executor = self._db._trust_executor
  :320  executor = self._db._trust_executor
  :339  executor = self._db._trust_executor
  :371  executor = self._db._trust_executor
  :557  result = self._db._trust_executor.apply_result_filter(result, plan)
  :785  records = self._db._trust_executor.apply_result_filter(records, plan)
  :882  record = self._db._trust_executor.apply_result_filter(record, plan)

rg '_audit_store' packages/kailash-dataflow/src/dataflow/trust/query_wrapper.py
  :1307  # Docstring — "attached to self._dataflow as _audit_store"
  :1314  store_event_id = await self._record_to_audit_store(...)
  :1340  await self._record_to_audit_store(...)
  :1352  async def _record_to_audit_store(...)
  :1365  store = getattr(self._dataflow, "_audit_store", None)
  :1388  "trust.audit_store.record_failed"
```

**Verdict:** `_trust_executor` + `_audit_store` are actually wired into the hot path via `express.py` and `query_wrapper.py`. Phase 5.11 fix confirmed — for these two managers only. `_tenant_trust_manager` was missed (see HIGH-2 above).

---

## Facade → call-site → Tier 2 test table (DataFlow top-level)

| Facade attribute                       | First production call site                                                                | Tier 2 test filename                                               |
| -------------------------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `db.express`                           | `features/express.py` (entry point — used by every CRUD)                                  | `tests/integration/*` (thousands of call sites)                    |
| `db.express_sync`                      | `features/express.py::SyncExpress` (entry point)                                          | `tests/integration/sync_express_*`                                 |
| `db.bulk`                              | User-facing: `test_bulk_upsert_delegation_integration.py` (10 call sites)                 | `tests/integration/bulk_operations/*`                              |
| `db.transactions`                      | User-facing via `db.transactions.begin()` — exercised in `features/transactions.py` tests | `tests/integration/transactions/*`                                 |
| `db.connection`                        | Internal plumbing; no direct caller outside accessor                                      | Covered transitively by every DataFlow operation                   |
| `db.tenants` (`_multi_tenant_manager`) | ⚠️ Property only; zero call sites inside framework source (search `db\.tenants\.` = 0)    | NONE — MEDIUM, see below                                           |
| `db.cache`                             | `engine.py` + `classification/policy.py` + `features/retention.py` (4 reads)              | Covered by `tests/integration/cache/*`                             |
| `db.express._trust_executor`           | `features/express.py:308,320,339,371,557,785,882` — hot path ✅                           | `tests/regression/test_phase_5_11_trust_wiring.py` ⚠️ monolithic   |
| `db._audit_store`                      | `trust/query_wrapper.py:1365` — hot path ✅                                               | same file as above                                                 |
| `db._tenant_trust_manager`             | ❌ ZERO call sites — HIGH-2 orphan                                                        | NONE — HIGH                                                        |
| `db.retention`                         | `features/retention.py::RetentionEngine` — tests present                                  | `tests/integration/retention/*`                                    |
| `db.schema_state_manager`              | `migrations/schema_state_manager.py` — caller is migration framework itself               | `tests/integration/migrations/test_schema_state_manager*`          |
| `db.tenant_context`                    | Property; internal use only                                                               | `tests/unit/tenant/*`                                              |
| `db.classification_policy`             | `classification/policy.py` — used by `_trust_executor` path                               | covered via Phase 5.11 test + `tests/integration/classification/*` |
| `db.audit`                             | `core/audit_integration.py::AuditIntegration` — tested                                    | `tests/integration/audit/*`                                        |
| `db.fabric`                            | `fabric/*` — full subsystem; read by operators                                            | `tests/integration/fabric/*`                                       |

### Sub-observation: `db.tenants` (MultiTenantManager)

- Property at `engine.py:3059` returns `self._multi_tenant_manager`
- Only set-site: `engine.py:595`
- Internal read: ZERO (`rg 'self\._multi_tenant_manager\.' = zero method calls, only property return at :3062`)
- Downstream read: `rg 'db\.tenants\.' = 0` — no caller exercises the methods
- Classification: **possible orphan** but the class is a public-API convenience for downstream users. Not HIGH because the property itself is the contract — callers `db.tenants.X()` are possible but none exist in-tree.
- **Recommended follow-up (future round):** confirm via documentation whether `db.tenants` is a public API. If yes → keep + add Tier 2 test. If no → delete.

---

## Nexus + Kaizen + Core SDK facade scan

**Nexus** (`packages/kailash-nexus/src/nexus/core.py`) — public properties all return data-shape values (`routes`, `middleware`, `routers`, `fastapi_app`, `websocket_handlers`, `_workflows`, `_gateway`). No `*Manager` / `*Executor` / `*Store` / `*Registry` / `*Engine` / `*Service` property returning an instance that lacks a call site. Clean.

**Kaizen** (`packages/kailash-kaizen/src/kaizen/`) — `StreamingExecutor` + `BaseAgent` + `Delegate` are all invoked from `execution/streaming_executor.py` and `agents/`. No top-level facade orphans surfaced by grep. Clean.

**Core SDK** (`src/kailash/`) — `RequestDeduplicator` + `EventStore` (from `servers/durable_workflow_server.py`) are lazy-init properties. Both have call sites inside the server's request-handling path. Clean.

---

## MEDIUM — Wiring-test file naming non-compliance

**Rule:** `rules/facade-manager-detection.md` Rule 2 mandates `test_<lowercase_manager_name>_wiring.py` per facade.

**Current state:** `test_phase_5_11_trust_wiring.py` is a monolithic file covering `_trust_executor`, `_audit_store`, AND `_tenant_trust_manager`. The file name encodes a phase, not a facade. A reviewer searching for `test_tenant_trust_manager_wiring.py` grep-misses and assumes the wiring is untested — which is actually correct, because (as HIGH-2 shows) it has no wiring at all.

**Disposition:**

- Split into three files: `test_trust_executor_wiring.py`, `test_audit_store_wiring.py`, `test_tenant_trust_manager_wiring.py` (the last one goes away if HIGH-2 is resolved by deletion).
- Update each to assert externally-observable effects (current file asserts `is not None`; should assert audit row / redacted field / cross-tenant reject).

---

## Test-file orphans (recently-deleted sources)

`git log --name-status -20 --diff-filter=D` output summary:

- Commit `e550949c` (2026-04-18): deleted 6 orphan test files for `dataflow.migration` (singular) — test-API removed in 2026-04-08 via `53dab715`.
- Commit `5edc941f` (2026-04-16): deleted 1 orphan file importing `BulkDeleteNode`.
- Commit `d3e7e0ef` (2026-04-16): deleted 8 orphan files importing `BulkCreateNode/BulkDeleteNode/BulkUpdateNode`.

**Current state:** `pytest --collect-only` runs clean on all four test trees (5839 + 2044 + 11189 + 15959 = 35,031 tests, zero ModuleNotFoundError, zero ImportError). `rules/orphan-detection.md` Rule 4 (API removal sweeps tests) + Rule 5 (collect-only merge gate) currently green.

---

## Bulk-upsert WARN-on-error behavior verification

**File:** `packages/kailash-dataflow/src/dataflow/nodes/bulk_upsert.py:360-382`

```python
except Exception as batch_error:
    err_str = str(batch_error)
    logger.warning(
        "bulk_upsert.batch_error: %s",
        err_str,
        extra={"error": err_str, "batch_size": len(batch)},
    )
    batch_errors.append(err_str)
    # Continue processing later batches: callers receive partial
    # success in (rows_affected, inserted, updated) and the
    # accumulated `batch_errors` list.

if batch_errors and batches_attempted == len(batch_errors):
    raise NodeExecutionError(
        f"bulk_upsert: all {batches_attempted} batch(es) failed; "
        f"first_error={batch_errors[0]}"
    )
```

**Verdict:** ✅ Compliant with `rules/observability.md` Rule 7:

- WARN log emitted on every batch error (line 364).
- Structured fields `error` and `batch_size` included.
- Fail-loud branch at line 376 raises `NodeExecutionError` when EVERY batch fails — no silent no-op success.

The module-level `logger = logging.getLogger(__name__)` at line 7 provides the required structured logger. Issue #494 session notes concern was about this path — confirmed correctly implemented.

---

## Disposition — action items for next round

1. **HIGH-1** → open issue or file against existing Issue #494: "bulk_upsert pool path is dead code — delete OR implement `operation='execute'` in `DataFlowConnectionManager`". No middle ground.
2. **HIGH-2** → new issue: "`_tenant_trust_manager` facade orphan — instantiate without production call site". Port Phase 5.11 fix pattern.
3. **MEDIUM** → refactor `test_phase_5_11_trust_wiring.py` into three files per `rules/facade-manager-detection.md` Rule 2 when HIGH-2 is addressed.
4. **Watch** → `db.tenants` property — confirm public-API status; currently has zero internal consumers.
5. **Clean carry-through** → Phase 5.11 fix for `_trust_executor` + `_audit_store` verified intact; no regression.

## Evidence commands (reproduce from repo root)

```bash
# HIGH-1 verification
sed -n '156,171p' packages/kailash-dataflow/src/dataflow/nodes/workflow_connection_manager.py
sed -n '615,635p' packages/kailash-dataflow/src/dataflow/nodes/bulk_upsert.py

# HIGH-2 verification (zero call sites)
rg '_tenant_trust_manager\.' packages/ src/
rg 'tenant_trust_manager\.' packages/ src/

# Phase 5.11 wired-ness verification
rg 'self\._db\._trust_executor' packages/kailash-dataflow/src/dataflow/features/express.py -n

# Collect-only merge gate
.venv/bin/python -m pytest --collect-only packages/kailash-dataflow/tests/ 2>&1 | tail -2
.venv/bin/python -m pytest --collect-only packages/kailash-nexus/tests/ 2>&1 | tail -2
.venv/bin/python -m pytest --collect-only packages/kailash-kaizen/tests/ 2>&1 | tail -2
.venv/bin/python -m pytest --collect-only tests/ 2>&1 | tail -2

# Bulk-upsert WARN verification
sed -n '360,382p' packages/kailash-dataflow/src/dataflow/nodes/bulk_upsert.py
```
