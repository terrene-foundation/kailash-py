# Issue #1050 — Write-Protection Engine Orphan: Fix Design

CRITICAL security defect. `ProtectedDataFlow` write protection
(`enable_read_only_mode`, `production_safe`, `add_model_protection`,
business-hours/field protection) is configured but never enforced on any real
DataFlow path. `WriteProtectionEngine.check_operation()` is unreachable.

This document is the `/analyze` design deliverable. It selects an insertion
point, specifies the exact method/wrapper to add, and lists decomposition work
units for `/todos`. Nothing is implemented.

Root cause is treated as ground truth per the brief (independently confirmed by
two parallel agents; see `01-rootcause-verification.md`). This document
re-grounded every cited file:line against the source before relying on it.

---

## 0. Root-cause restatement (verified file:line)

The protection engine has exactly two production call sites, both synchronous,
both on dead code paths:

- `protection_middleware.py:367` — `ProtectedNode.run()` (sync; class
  `protect_dataflow_node()` at `:279-391`, the sync `run` body at `:294-385`,
  the `check_operation()` call at `:366-372`).
- `protection_middleware.py:422` — `AsyncSQLProtectionWrapper.protected_execute()`
  (a **sync** `def` closure at `:412`, wrapping the sync `original_execute`;
  class `:394-451`).

`_handle_violation` (`protection.py:414-425`) re-raises the `ProtectionViolation`
when `level ∈ {BLOCK, AUDIT}`. `check_operation()` itself is at
`protection.py:302-392`; its operation-string→`OperationType` map is
`protection.py:290-300` and accepts `create / read / update / delete / list /
bulk_create / bulk_update / bulk_delete / bulk_upsert`.

Why both call sites are dead:

1. Generated node `DataFlowNode(AsyncNode)` is created at `nodes.py:498`. Its
   real work is `async_run()` (`nodes.py:1472`). Its sync `run()`
   (`nodes.py:1459-1470`) is only a thin `async_safe_run(self.async_run(...))`
   wrapper.
2. `protect_dataflow_node()` (`protection_middleware.py:287`) subclasses the
   node and overrides **only `run()`**. It never overrides `async_run()` or
   `execute_async()`.
3. `AsyncNode.execute()` (`base_async.py:98-145`) never calls `run()`. On every
   branch it calls `asyncio.run(self.execute_async(...))` (`:142`),
   `_execute_in_thread` (`:137`→`:158`), or `_execute_in_new_loop`
   (`:145`→`:175`) — all route to `execute_async()`. `AsyncNode.run()`
   (`base_async.py:180-192`) is hard-wired to `raise NotImplementedError`.
4. `AsyncNode.execute_async()` (`base_async.py:214-282`) calls
   `await self.async_run(...)` at `:260`. It never touches `run()`. Its
   `except` block re-raises ONLY `NodeValidationError` (`:271-273`) /
   `NodeExecutionError` (`:274-276`) as-is; `except Exception`
   (`:277-282`) WRAPS everything else in `NodeExecutionError` — the
   red-team-surfaced exception-taxonomy constraint that §2.1 addresses.
5. `runtime/local.py` dispatch prefers `execute_async` over sync execution on
   both paths: std path `4236-4242` (`if hasattr(node,"execute_async")` first),
   async-runtime path `3137-3140` (`if self.enable_async and hasattr(...,
"execute_async")`).
6. Express bypasses the runtime entirely and calls `await node.async_run(...)`
   directly. Verified call sites in `features/express.py`:
   create `:623`, read `:730`, update `:808`, delete `:894`, list
   `:1000` and `:1096`, count `:1170`, upsert `:1233`, upsert_advanced `:1312`,
   bulk_create `:1377`, bulk_delete `:1505`, bulk_upsert `:1584`, plus the file
   import surface `:1886`/`:2311`. Each Express op instantiates the node via
   `_create_node()` (`express.py:213-226`), which calls `node_class()` then sets
   `node.dataflow_instance = self._db` (`:225`).

Net: the sync `ProtectedNode.run()` override is never invoked by Express, by
`LocalRuntime`, by `AsyncLocalRuntime`, or by a raw `node.execute()` sync caller
(because `AsyncNode.execute()` reroutes to `execute_async`→`async_run`). The
`AsyncSQLProtectionWrapper.protected_execute` wrapper is likewise a sync `def`
wrapping `AsyncSQLDatabaseNode.execute` — but the DataFlow node calls the async
SQL path, not the sync `execute`, so it is the same dead-sync-wrapper failure
mode. **`check_operation()` is an orphan** (`orphan-detection.md` §1,
`facade-manager-detection.md` — `WriteProtectionEngine` is an `*Engine`
manager-shape class with zero hot-path call site).

---

## 1. Insertion-point analysis

Three candidate insertion points. For each: coverage, call-site count,
double-invocation risk, DataFlow invariant impact.

### P1 — Override `async_run()` (and the `execute_async` question) in `ProtectedNode`

Mirror the existing sync `run()` protection inside
`protect_dataflow_node()`: add an `async def async_run(self, **kwargs)` to the
`ProtectedNode` subclass that performs the same `check_operation()` call the
sync `run()` does, then `return await super().async_run(**kwargs)`.

- **Paths covered**: ALL of them. Express (`await node.async_run()`),
  `LocalRuntime` / `AsyncLocalRuntime` (which call `execute_async()` →
  `super().async_run()` → the override), and raw `node.execute()` /
  `node.async_run()` callers. This is the single chokepoint every real path
  funnels through (`base_async.py:260` always calls `self.async_run`; the MRO
  resolves it to `ProtectedNode.async_run`).
- **Call-site count to add**: 1 method, in 1 function
  (`protect_dataflow_node`). The decorator is already applied at two places
  (`protected_engine.py:46` via `ProtectedNodeGenerator._create_node_class`,
  and `protected_engine.py:154` in `ProtectedDataFlow.model()`); both inherit
  the new method automatically. Zero Express edits, zero runtime edits.
- **Double-invocation risk**: The sync `run()` (`nodes.py:1459`) calls
  `async_safe_run(self.async_run(**kwargs))`. With the decorator, MRO makes
  `self.run` → `ProtectedNode.run` (checks) → `async_safe_run` →
  `self.async_run` → `ProtectedNode.async_run` (checks AGAIN). A sync caller
  that reaches `ProtectedNode.run()` would double-check. **Mitigation is
  mandatory and simple**: delete the `run()` override from
  `protect_dataflow_node` and keep ONLY the `async_run()` override. The sync
  `run()` then resolves to the unprotected `DataFlowNode.run()`
  (`nodes.py:1459`), which calls `self.async_run()` → the protected
  `ProtectedNode.async_run()`. One check, on every path, no double-invocation.
  (The sync `run()` override is dead today anyway — removing it loses no
  coverage and removes the only double-check vector.)
- **DataFlow invariant impact**:
  - _Connection pool / session lifecycle_: the check runs BEFORE
    `super().async_run()`, i.e. before `ensure_table_exists()`
    (`nodes.py:1486-1532`) and before any pool acquisition. A blocked op
    raises before a connection is taken — strictly better than the sync `run()`
    placement and no pool/session change.
  - _Tenant / clearance context_: `check_operation` does not need tenant or
    clearance; it needs `(operation, model_name, connection_string, context)`.
    All four are available on `self` inside `async_run`: `self.operation`
    (`nodes.py:638`), `self.model_name` (`nodes.py:637`),
    `self.dataflow_instance.database_url` (the existing sync `run()` already
    resolves connection string this way at `protection_middleware.py:358-363`),
    and `context = {"node_id", "model_fields", "inputs": kwargs}` exactly as
    the sync override builds it (`protection_middleware.py:351-356`).
  - _Operation-string mapping_: `self.operation` is already the canonical
    lowercase string (`create`/`read`/`update`/`delete`/`list`/`count`/
    `upsert`/`bulk_create`/...). It maps directly through
    `_operation_mapping` (`protection.py:290-300`) — NO class-name parsing
    needed. The sync override's brittle class-name string parsing
    (`protection_middleware.py:321-349`) is REPLACED by reading
    `self.operation` directly. This also fixes a latent bug: the sync override
    maps `upsert`/`count` to `"unknown"` (its if-ladder only handles
    Create/Update/Delete/Read/List), whereas `self.operation` is exact.

### P2 — Express-layer hook before each `node.async_run()` call site

Add `await self._protection_check(model, operation)` immediately before each of
the ~13 `node.async_run()` calls in `features/express.py`, modeled on the
existing `_trust_check_write` / `_trust_check_read` precedent
(`express.py:344-373`, already called before every mutation, e.g.
`create` calls `_trust_check_write` at `:620`).

- **Paths covered**: Express ONLY. The `runtime.execute(workflow.build())`
  path (LocalRuntime/AsyncLocalRuntime executing generated nodes in a
  WorkflowBuilder graph) does NOT go through Express — it dispatches the node
  directly (`local.py:4236-4242` / `3137-3140`). A user who builds a workflow
  with `TestModelCreateNode` and runs it on a protected runtime would NOT be
  protected. **This fails the brief's "MUST cover BOTH Express AND
  `runtime.execute(workflow.build())`" requirement.**
- **Call-site count to add**: ~13 (every `async_run` site enumerated in §0
  item 6). High drift surface — this is exactly the multi-site-plumbing
  failure mode `security.md` § "Multi-Site Kwarg Plumbing" warns against; one
  missed sibling = a silent protection bypass.
- **Double-invocation risk**: None by itself. But if P2 is combined with P1
  to also cover the runtime path, every Express op double-checks (Express
  hook + node `async_run` hook). Combining P2+P1 is therefore wrong.
- **DataFlow invariant impact**: Express already owns model name + operation
  string at each call site (it passes `model`, `"Create"` etc. to
  `_create_node`). Connection string is `self._db.database_url`. No
  pool/session/tenant concern. But the coverage gap (workflow-runtime path)
  is disqualifying on its own.

### P3 — Async wrapper in `AsyncSQLProtectionWrapper`

Convert `AsyncSQLProtectionWrapper.protected_execute` (currently sync `def` at
`protection_middleware.py:412`) into an async wrapper of
`AsyncSQLDatabaseNode.execute_async` / its async run path, doing SQL-string
operation detection (`_detect_operation_from_sql`,
`protection_middleware.py:436-451`) then `check_operation()`.

- **Paths covered**: Only operations that flow through `AsyncSQLDatabaseNode`
  at the SQL-execution layer. DataFlow's generated node builds SQL and uses
  `AsyncSQLDatabaseNode` internally (imported at `nodes.py:1477`), so in
  principle this catches both Express and runtime paths. BUT:
  - It enforces at the SQL-string layer using regex operation-detection
    (`startswith("INSERT")` etc.), which is fragile vs the exact
    `self.operation` available at P1. CTEs, `INSERT ... RETURNING`, dialect
    quirks, and DataFlow's own multi-statement bulk paths can mis-detect.
  - It loses `model_name` (the wrapper only sees SQL text + connection
    string), so **model-level and field-level protections
    (`add_model_protection`, `add_field_protection`) cannot be enforced** —
    `check_operation` needs `model_name` for `model_protections` matching
    (`protection.py:349-389`). This guts a documented feature.
  - `node_class.execute = protected_execute` (`protection_middleware.py:433`)
    mutates the shared `AsyncSQLDatabaseNode` class globally — a
    process-wide monkeypatch affecting every DataFlow instance, not just the
    protected one. Cross-instance contamination.
- **Call-site count**: 1 (the wrapper), but with a global class-mutation
  side effect.
- **Double-invocation risk**: AsyncSQLDatabaseNode may be invoked multiple
  times per logical DataFlow op (e.g. table-exists DDL probe + the actual
  DML), causing repeated checks per user operation, some on internal DDL
  (`CREATE TABLE` from `ensure_table_exists`) that the user never asked for —
  spurious `custom_query` violations.
- **DataFlow invariant impact**: Worst of the three. Loses model/field
  granularity, global class mutation breaks instance isolation, and SQL-regex
  detection is unreliable. Disqualified.

### Comparison summary

| Criterion                            | P1 (async_run override)           | P2 (Express hook) | P3 (AsyncSQL wrapper)  |
| ------------------------------------ | --------------------------------- | ----------------- | ---------------------- |
| Express path                         | ✅                                | ✅                | ✅ (SQL layer)         |
| `runtime.execute(workflow.build())`  | ✅                                | ❌                | ⚠️ (SQL layer only)    |
| Raw `node.execute()` / `async_run()` | ✅                                | ❌                | ⚠️                     |
| Call sites to add                    | **1**                             | ~13               | 1 + global mutation    |
| Double-check vector                  | removable (drop `run()` override) | none alone        | yes (per-statement)    |
| model/field protection               | ✅ (`self.model_name`)            | ✅                | ❌ (no model name)     |
| Op detection accuracy                | exact (`self.operation`)          | exact             | regex (fragile)        |
| Instance isolation                   | ✅                                | ✅                | ❌ (class monkeypatch) |

---

## 2. Recommended design

**Primary insertion point: P1 — add `async def async_run()` to the
`ProtectedNode` subclass inside `protect_dataflow_node()`
(`protection_middleware.py:287-391`), and DELETE the existing sync `run()`
override from the same class — PAIRED WITH the §2.1 exception-taxonomy
fix (Option (a): re-base `ProtectionViolation` onto `NodeExecutionError`).**

P1 places the `check_operation` call at the single chokepoint every path
funnels through (`async_run`), with exactly one new method, zero
call-site plumbing, and no double-check. But P1 ALONE is insufficient:
on the workflow-runtime path, `AsyncNode.execute_async`
(`base_async.py:277-282`) wraps the raised `ProtectionViolation` in
`NodeExecutionError`, violating spec invariant I5 for plain
`LocalRuntime`/`AsyncLocalRuntime` callers (red-team finding, see §2
"Workflow-runtime path — CORRECTED" and §2.1). The MINIMAL complete fix
is P1 (chokepoint) + Option (a) (taxonomy) — together they cover the
Express path (P1, genuine type, direct `async_run` call), the
workflow-runtime path (P1 raises + Option (a) makes
`execute_async`'s `except NodeExecutionError: raise` re-raise the
genuine subclass type unwrapped), and raw callers. The Express path is
satisfied by P1 alone; the workflow-runtime path requires both.

### Exact change

In `protect_dataflow_node()` (`protection_middleware.py:279-391`):

1. **Remove** the `def run(self, **kwargs)` override (`:294-385`). Its only
   effect today is to add a dead double-check vector; the unprotected
   `DataFlowNode.run()` (`nodes.py:1459`) is a correct sync→async bridge and
   will reach the new protected `async_run()`.

2. **Add** `async def async_run(self, **kwargs) -> Dict[str, Any]:` that:
   - resolves the protection engine via the same guard the sync override used:
     `if hasattr(self, "dataflow_instance")` and
     `hasattr(df, "_protection_engine")` and `df._protection_engine is not
None` (`protection_middleware.py:306-319`). Express binds
     `dataflow_instance` at `express.py:225`; the workflow path binds it via
     the node generator (`nodes.py:639`). Both populate it before `async_run`.
   - builds `check_operation` arguments from `self`, NOT from class-name
     parsing: - `operation = self.operation` (`nodes.py:638`) — already canonical,
     maps through `_operation_mapping` (`protection.py:290-300`). Replaces
     the brittle, incomplete class-name if-ladder
     (`protection_middleware.py:321-349`) which mis-maps `upsert`/`count`. - `model_name = self.model_name` (`nodes.py:637`). - `connection_string`: `kwargs.get("database_url")` then fall back to
     `self.dataflow_instance.database_url` — identical resolution to the
     removed sync override (`protection_middleware.py:358-363`). - `context = {"node_id": getattr(self,"node_id","unknown"),
"model_fields": getattr(self,"model_fields",{}), "inputs": kwargs}` —
     identical to `protection_middleware.py:351-356`.
   - calls `protection_engine.check_operation(operation=..., model_name=...,
connection_string=..., context=...)` inside `try/except
ProtectionViolation` and `raise`s (do NOT swallow). `check_operation`
     itself calls `_handle_violation` which raises for BLOCK/AUDIT and only
     logs for WARN (`protection.py:414-425`) — so a WARN-level config does NOT
     raise, preserving the documented WARN semantics.
   - on pass, `return await super().async_run(**kwargs)`. `super()` resolves
     to `DataFlowNode.async_run` (`nodes.py:1472`) via the MRO
     (`ProtectedNode(original_class)` where `original_class` is the generated
     `DataFlowNode`).

`check_operation` is synchronous and CPU-only (dict lookups, regex
`re.match` on connection string, time-window checks) — calling it directly
inside `async_run` without `await` is correct; it does no I/O.

### Why arguments are correct at this point

`async_run` runs on the bound node instance. By the time any real path reaches
it, `self.operation`, `self.model_name`, `self.dataflow_instance`, and
`self.model_fields` are all set in `DataFlowNode.__init__` (`nodes.py:634-648`)
and `dataflow_instance` is (re)bound by Express `_create_node`
(`express.py:225`) or the workflow node generator. The check executes BEFORE
`super().async_run()` → before `ensure_table_exists` → before pool acquisition,
so a blocked write never takes a connection.

### Exception propagation (verified end-to-end)

`ProtectionViolation` is a plain `Exception` subclass (`protection.py:163-181`).
Propagation:

- `ProtectedNode.async_run` raises `ProtectionViolation` →
- `DataFlowNode.run` path: `async_safe_run` re-raises (sync callers) — but the
  sync path is not the concern; the async paths are:
- **Express path**: `create` wraps `await node.async_run(**data)` in
  `try/except Exception as exc:` (`express.py:621-628`) which calls
  `_trust_record_failure` and **`raise`s** (`:628`). It does NOT swallow into a
  result dict — verified for create (`:624-628`), read (`:751-779`, with the
  caveat below), update (`:809-819`), delete (`:895-903`), list
  (`:1001-1005`), count (`:1171-1175`). So `ProtectionViolation` surfaces to
  the Express caller as a real raised exception. ✅
  - _read() caveat_: `read`'s `except Exception` (`express.py:751-779`)
    converts "not found"-class errors to `return None` via a substring check
    on `str(e).lower()` (`:753-758`). `ProtectionViolation`'s message is
    `"Global protection blocks read"` / `"Model protection blocks read: ..."`
    (`protection.py:328`,`:362`,`:378`) — none contain "not found" / "no
    record" / "does not exist", so it correctly falls through to
    `_trust_record_failure` + `raise` (`:772-779`). No design change needed,
    but a Tier-2 test MUST assert read-protection raises (not returns None) to
    pin this.
- **Workflow-runtime path** — CORRECTED (was a factual error in the prior
  draft; red-team confirmed):
  `AsyncNode.execute_async` (`base_async.py:214-282`) wraps the
  `await self.async_run` call (`:260`) in a `try/except` whose re-raise
  allowlist is EXACTLY two types: `except NodeValidationError: raise`
  (`:271-273`) and `except NodeExecutionError: raise` (`:274-276`).
  The third handler — `except Exception as e:` (`:277`) — calls
  `raise NodeExecutionError(f"Node '{self.id}' execution failed:
{type(e).__name__}: {e}") from e` (`:280-282`). A plain
  `ProtectionViolation(Exception)` (`protection.py:163`) is NOT in the
  allowlist, so it falls to the `:277` handler and is **wrapped in
  `NodeExecutionError`** — the original `ProtectionViolation` survives
  only as `__cause__` (the `from e` chain). The runtime then propagates
  that `NodeExecutionError` to the caller (`local.py:4243-4245`).
  **Consequence: on the workflow-runtime path
  (`runtime.execute(workflow.build())` /
  `AsyncLocalRuntime.execute_workflow_async`), a blocked write raises
  `NodeExecutionError`, NOT `ProtectionViolation`.** P1 alone does NOT
  satisfy spec invariant I5 ("a raised `ProtectionViolation` MUST
  propagate to the caller") on §2 path 2 for plain `LocalRuntime` /
  `AsyncLocalRuntime` callers. The exception-taxonomy fix in §2.1 below
  is REQUIRED in addition to P1.
  - `ProtectedDataFlowRuntime.execute` (`protection_middleware.py:50-98`)
    DOES still re-raise a fresh `ProtectionViolation` by string-matching
    the results-dict `error` field (`:64-96`) — BUT that helps ONLY users
    who construct `db.create_protected_runtime()`. A user running a
    workflow on a plain `LocalRuntime` against a protected `db` (the
    documented "use protected runtime" example is one path; a plain
    runtime executing protected nodes is another) gets the
    `NodeExecutionError`. The contract surface (spec §2 path 2) is "the
    workflow-runtime path", not "the protected-runtime path" — so the
    taxonomy fix is mandatory, not optional.
- **Express path** — UNCHANGED, propagates cleanly (red-team confirmed,
  incl. bulk). Express calls `await node.async_run(**data)` DIRECTLY
  (e.g. `express.py:623`), NOT via `execute_async`. The `execute_async`
  re-wrap is therefore never on the Express path; the
  `ProtectionViolation` raised by `ProtectedNode.async_run` reaches
  Express's `except Exception as exc: ... raise` (create `:624-628`,
  update `:809-819`, delete `:895-903`, list `:1001-1005`, count
  `:1171-1175`, bulk_create `:1377`-adjacent, bulk_delete `:1505`,
  bulk_upsert `:1584`) as the genuine `ProtectionViolation` type. The
  `read()` not-found→`None` substring filter (`:751-779`) does not catch
  it (message is "protection blocks", not "not found"). Express is fine
  with P1 alone.

## 2.1 Exception-taxonomy fix (REQUIRED for I5 on the workflow-runtime path)

P1 raises a genuine `ProtectionViolation`, but `AsyncNode.execute_async`
(`base_async.py:277-282`) wraps it in `NodeExecutionError` on the
workflow-runtime path (§2 "Workflow-runtime path — CORRECTED"). Spec
invariant I5 requires the caller to receive `ProtectionViolation`. Three
options to make it survive `execute_async`:

### Option (a) — `class ProtectionViolation(NodeExecutionError)` — RECOMMENDED

Re-base `ProtectionViolation` (currently `class ProtectionViolation(Exception)`,
`protection.py:163-181`) onto `kailash.sdk_exceptions.NodeExecutionError`.
Then `execute_async`'s `except NodeExecutionError: raise` (`base_async.py:274-276`)
re-raises the ACTUAL `ProtectionViolation` instance with its type intact —
no wrap. `except ProtectionViolation` callers still match (subclass
relationship). The runtime propagates the genuine type to the caller. I5
holds on every path.

- **Dependency direction (verified clean):** `protection.py` would add
  `from kailash.sdk_exceptions import NodeExecutionError`. `dataflow`
  importing from core `kailash` is correct and already pervasive
  (`packages/kailash-dataflow/src/dataflow/nodes/*.py` already do
  `from kailash.sdk_exceptions import NodeExecutionError` — e.g.
  `bulk_upsert.py:13`, `transaction_nodes.py:21`). Core MUST NOT import
  `dataflow`; this change does not invert that — it is dataflow→core,
  the allowed direction.
- **Blast-radius grep results** (`grep -rn 'except NodeExecutionError'`
  across `src/kailash/` + `packages/kailash-dataflow/src/`, excluding
  `.venv/` and `build/lib/` which are non-source build artifacts):
  - **Re-raise-allowlist sites (by design, behavior IMPROVED):**
    `base_async.py:274` (the target — now re-raises the genuine
    `ProtectionViolation`), `base.py:1577`/`:2174` (sync `Node.execute`
    re-raise allowlist — identical by-design `except NodeExecutionError:
raise` pattern; a `ProtectionViolation` reaching these now re-raises
    cleanly instead of being re-wrapped — strict improvement, no
    swallow). DataFlow nodes are `AsyncNode`, so the `base.py` sync path
    is not the DataFlow hot path anyway.
  - `async_sql.py:4545`, `:4622`, `:5520` — all are
    `except NodeExecutionError: raise` (verified: `:4545-4547`
    "Re-raise our own errors", `:4622-4624`, `:5520-5523` retry-loop
    re-raise). Same by-design re-raise shape. A `ProtectionViolation`
    is never raised from inside `AsyncSQLDatabaseNode` (the protection
    check fires at the DataFlow node layer ABOVE `AsyncSQLDatabaseNode`,
    in `ProtectedNode.async_run`, before SQL execution). These sites
    cannot receive a `ProtectionViolation`. No behavior change.
  - `security_access_control.py:147` —
    `except (NodeExecutionError, Exception) as e: return {"success":
False, "error": str(e), "allowed": False}`. The tuple includes
    bare `Exception`, so it ALREADY catches `ProtectionViolation`
    today (it is an `Exception` subclass now). Re-basing to
    `NodeExecutionError` does NOT change the match — `(NodeExecutionError,
Exception)` catches both forms identically. AND this is
    `SecurityAccessControlNode`, a DIFFERENT node type, not on the
    DataFlow generated-CRUD path. No behavior change, no incorrect
    swallow introduced.
  - `mcp_executor.py:372`, `code/python.py:1441` — `except
NodeExecutionError:` on unrelated node types (MCP executor,
    PythonCodeNode); not on the DataFlow CRUD path; cannot receive a
    `ProtectionViolation`. No behavior change.
  - **Conclusion:** zero production `except NodeExecutionError` site
    would incorrectly swallow or mis-handle a `ProtectionViolation`
    after the re-base. Every site is either a by-design re-raise
    (behavior strictly improves — genuine type instead of wrap) or on a
    node type that never raises `ProtectionViolation`.
  - **`except ProtectionViolation` sites (verified compatible):**
    `protection_middleware.py:373` (the dead sync `run()` override —
    being DELETED by P1 anyway), `:427` (`AsyncSQLProtectionWrapper` —
    dead, out of scope, flagged WU-5). `examples/*.py` (6 sites) and
    `tests/**` (`test_protection_system_critical_gaps.py:393/448/469/539/580`,
    `test_write_protection_comprehensive.py`,
    `test_critical_write_protection_e2e.py`) all use
    `except ProtectionViolation` / `pytest.raises(ProtectionViolation)`
    / `isinstance(x, ProtectionViolation)` — ALL still match after the
    re-base (subclass IS-A relationship preserves `except`/`isinstance`/
    `pytest.raises`). No test or example breaks.
- **Pros:** one-line class-statement change; makes I5 hold on ALL paths
  (Express + workflow-runtime + raw) with no per-runtime special-casing;
  preserves every existing `except ProtectionViolation` caller; the
  genuine type (with `.operation`, `.level`, `.model`, `.field` attrs,
  `protection.py:166-181`) reaches the caller instead of a stringified
  wrap.
- **Cons (real):** `ProtectionViolation` becomes a `NodeExecutionError`
  subclass — a public exception base-class change. Any downstream user
  who does `except NodeExecutionError` in their OWN code will now also
  catch `ProtectionViolation` (previously it escaped that handler). This
  is a behavior change for downstream code, MUST be a CHANGELOG entry.
  Mitigation: this is the _correct_ taxonomy — a protection block IS a
  node-execution failure; a downstream `except NodeExecutionError` that
  wants to treat "blocked by policy" differently can add an explicit
  `except ProtectionViolation` BEFORE it (MRO ordering). Document the
  precedence pattern in the CHANGELOG.
- **Cons:** changes `protection.py`'s import surface (adds a core
  `kailash` import) — but this is the allowed dataflow→core direction
  and the sibling `dataflow/nodes/*.py` files already do exactly this.

### Option (b) — Raise a type already in the allowlist

`ProtectedNode.async_run` could itself raise `NodeExecutionError(...)`
(in the allowlist) instead of `ProtectionViolation`.

- **Rejected:** this DISCARDS the typed `ProtectionViolation`
  (`.operation`/`.level`/`.model`/`.field` attrs) that the contract and
  every `except ProtectionViolation` caller (examples + tests +
  `ProtectedDataFlowRuntime.execute` string-match) depend on. It also
  loses the distinction between "node failed to execute" and "node was
  policy-blocked" — exactly the information operators need. Violates I5's
  spirit (the caller gets `NodeExecutionError`, not `ProtectionViolation`).
  Would require rewriting every `pytest.raises(ProtectionViolation)` and
  the `ProtectedDataFlowRuntime` re-raise logic. Strictly worse than (a).

### Option (c) — Fire `check_operation` in a wrapper OUTSIDE `execute_async`

Override `execute_async` itself in `ProtectedNode` (not `async_run`),
doing the check BEFORE `super().execute_async()`.

- **Partially viable but rejected:** Express does NOT call
  `execute_async` — it calls `async_run` directly (`express.py:623`
  etc.). So a `check_operation` in an `execute_async` override would
  NOT cover the Express path at all — re-introducing the orphan on the
  documented 23x-faster default. Would require ALSO overriding
  `async_run` (back to P1) → two override points, double-check risk.
  Even if scoped to runtime-only, the raised `ProtectionViolation` from
  the `execute_async` override's pre-check still has to exit
  `execute_async` — and the override's own body is still inside the
  `try/except` if it calls `super().execute_async()` after the check…
  unless the check is BEFORE the `try`. Workable only with careful
  structuring AND still needs P1 for Express → strictly more complex
  than (a) for no benefit. Rejected.

### Recommendation: Option (a)

Re-base `ProtectionViolation` onto `NodeExecutionError`. It is the
minimal change that makes I5 hold on the workflow-runtime path, the
blast-radius grep shows zero incorrect-swallow sites, every existing
`except ProtectionViolation` / `pytest.raises` caller still matches via
subclassing, and the dependency direction (dataflow→core) is the allowed
one already used by sibling files. The only real cost is a documented
public-exception-taxonomy CHANGELOG entry — which is the _correct_
taxonomy, not a workaround.

### Reconciling Shard-2/3 test assertions with Option (a)

Tests on the **Express** path keep `pytest.raises(ProtectionViolation)`
(Express surfaces the genuine type — unchanged). Tests on the
**workflow-runtime** path (plain `LocalRuntime`/`AsyncLocalRuntime`)
ALSO use `pytest.raises(ProtectionViolation)` — and PASS, because
Option (a) makes `execute_async`'s `except NodeExecutionError: raise`
re-raise the genuine `ProtectionViolation` (it IS-A `NodeExecutionError`)
WITHOUT wrapping. No test needs `pytest.raises(NodeExecutionError)`; the
subclass relationship means `pytest.raises(ProtectionViolation)` is the
correct, strictest assertion on every path. WU-2's restored gap-tests
and WU-3's workflow-runtime test both assert
`pytest.raises(ProtectionViolation)` and both are satisfied by (a)+P1
together. (Had option (b) been chosen, the workflow-runtime tests would
have needed `pytest.raises(NodeExecutionError)` — another reason (b) is
worse: it weakens the assertion.)

### What is explicitly NOT changed

- `AsyncSQLProtectionWrapper` (P3) is left as-is for this fix (it is dead but
  out of scope; flag for follow-up deletion per `orphan-detection.md` §3 —
  see Risks).
- No Express edits, no runtime edits. The fix touches exactly TWO source
  files: `protection_middleware.py` (P1 — the `async_run` override + the
  `run()`-override deletion) and `protection.py` (Option (a) — the
  one-line `ProtectionViolation` base-class change + one import). No
  `nodes.py`, `express.py`, `base_async.py`, or `local.py` edits.

---

## 3. Decomposition input (for `/todos`)

Discrete work units. Sizing per `autonomous-execution.md` Per-Session Capacity
Budget (≤500 LOC load-bearing, ≤5–10 invariants, ≤3–4 call-graph hops).

The red-team finding splits the original WU-1+WU-2 single shard into
**1a** (exception-taxonomy fix + `except NodeExecutionError` call-site
audit) and **1b** (`async_run` override + gap-test restore). These are
distinct concerns: 1a is a public-exception-base-class change with a
cross-package call-site audit; 1b is the node-override wiring. Splitting
keeps each within the `autonomous-execution.md` ≤5-invariant /
≤3-4-hop budget and isolates the CHANGELOG-bearing taxonomy change from
the wiring change for independent review.

### WU-1a — Exception-taxonomy fix + call-site audit (Shard 1a)

Re-base `ProtectionViolation` onto `NodeExecutionError`
(`protection.py:163` + add `from kailash.sdk_exceptions import
NodeExecutionError`); CHANGELOG entry documenting the public-exception
taxonomy change + the `except ProtectionViolation`-before-`except
NodeExecutionError` precedence pattern for downstream callers; re-run
the blast-radius grep (`grep -rn 'except NodeExecutionError' src/kailash/
packages/kailash-dataflow/src/`) post-change to confirm zero
incorrect-swallow sites; run the full `except ProtectionViolation` /
`pytest.raises(ProtectionViolation)` test set (examples excluded) to
confirm subclass match holds.

- **Size:** ~5 LOC load-bearing (one class statement + one import) +
  CHANGELOG + audit. The LOAD is the audit, not the LOC.
- **Invariants (4, within budget):** {dependency-direction is
  dataflow→core only; every `except ProtectionViolation` caller still
  matches via subclass; every by-design `except NodeExecutionError:
raise` site now re-raises the genuine type without wrap; no
  node-type that raises `ProtectionViolation` is caught by a swallowing
  `except NodeExecutionError`}.
- **Call-graph hops:** ≤3 (`ProtectionViolation` ← `_handle_violation`
  raise ← `check_operation` ← `execute_async` re-raise allowlist).
- **Feedback loop:** the existing `test_protection_system_critical_gaps.py`
  - `test_write_protection_comprehensive.py` `pytest.raises(
ProtectionViolation)` suite is the live loop — fits comfortably.
- **One shard.** Lands BEFORE 1b (1b's gap-tests assert the genuine
  `ProtectionViolation` propagates through the runtime — that assertion
  only holds once 1a is in).

### WU-1b — `async_run` override + gap-test restore (Shard 1b)

Replace the sync `run()` override in `protect_dataflow_node()` with an
`async_run()` override; build args from `self.operation`/`self.model_name`/
`self.dataflow_instance` (not class-name parsing). PLUS, in the SAME
commit (per `orphan-detection.md` §4a — implementing the wiring MUST
sweep the gap-marker tests or release CI flips them red), restore the 2
intent-changed tests in `tests/unit/test_protection_system_critical_gaps.py`:

- `test_runtime_node_execution_interception_gap` (`:316-405`) — replace
  the isolated `check_operation` call (`:392-403`, `# KNOWN COVERAGE
GAP — tracked: issue #1050` block at `:384-391`) with a real
  `runtime.execute(workflow.build())` asserting
  `pytest.raises(ProtectionViolation)` propagates.
- `test_error_propagation_chain_gap` (`:407-455`) — replace the
  isolated-engine call (`:447-455`, marker `:441-446`) with the
  propagation-via-execution assertion.
- **Size:** ~40–60 LOC load-bearing (the override) + ~40 LOC test
  restore.
- **Invariants (5, at budget edge):** {exact operation-string mapping
  via `self.operation`; connection-string resolution; no-double-check
  (delete the sync `run()` override); WARN-vs-BLOCK semantics preserved;
  raise-not-swallow}.
- **Call-graph hops:** ≤3 (`async_run`→`check_operation`→
  `_handle_violation`).
- **Feedback loop:** the restored gap-tests + WU-3/WU-4 → live loop.
- **One shard.** Depends on 1a (the restored gap-tests assert
  `ProtectionViolation` survives the runtime path — true only post-1a).

### WU-3 — Workflow-runtime path coverage

A dedicated Tier-2 test: build a `WorkflowBuilder` with a generated
`*CreateNode`, run via **plain `LocalRuntime` AND `AsyncLocalRuntime`**
(NOT only `ProtectedDataFlowRuntime`) against a protected `db`, assert
`pytest.raises(ProtectionViolation)` under `enable_read_only_mode`. The
plain-runtime path is the one that exercises the
`execute_async` → `except NodeExecutionError: raise` re-raise — i.e. it
is the test that would FAIL with P1-only (before 1a) and PASS with
1a+1b. This test is the regression guard for the red-team finding
itself: it MUST assert `ProtectionViolation` (the genuine subclass type),
NOT `NodeExecutionError` — per the §2.1 reconciliation, the subclass
relationship makes `pytest.raises(ProtectionViolation)` the correct
strictest assertion on every path. Also assert
`isinstance(exc, NodeExecutionError)` in the same test to pin the
taxonomy contract (if a future refactor un-bases `ProtectionViolation`,
this line fails loudly — the structural-invariant pattern from
`cross-sdk-inspection.md` §3a). ~40 LOC. **One shard, depends on
1a+1b, can parallel WU-4.**

### WU-4 — Per-mutation-surface Tier-2 matrix

One Tier-2 integration test PER protected mutation surface, real Postgres AND
file-backed SQLite (#998 fixture precedent in the existing test file at
`:316-405`), asserting protection BLOCKS: create, update, delete, upsert,
bulk_create, bulk_update, bulk_delete, bulk_upsert — AND asserting protection
does NOT block: read, list, count (see Risks §4). Also a model-level
(`add_model_protection`) and field-level (`add_field_protection`) enforcement
test to prove `self.model_name` reaches `check_operation`. This is the
`facade-manager-detection.md` / `orphan-detection.md` §2 wiring proof
(`test_write_protection_engine_wiring.py`, facade-imported `db`, external
effect = the op raises). ~8–11 test methods, mostly boilerplate stamped from
one pattern (~250–350 LOC boilerplate). **One shard** per the boilerplate-scales
clause; if the real-Postgres + SQLite duplication pushes it past budget, shard
by {write-block tests} / {read-allow tests} / {model+field tests} — 3 shards.

### WU-5 — Orphan cleanup follow-up (separate, flag only)

`AsyncSQLProtectionWrapper` + the global `node_class.execute = protected_execute`
monkeypatch (`protection_middleware.py:394-451`, `protected_engine.py:163-173`)
are now provably dead. Per `orphan-detection.md` §3 (removed = deleted) this
should be deleted, but it is OUT OF SCOPE for the security fix and exceeds the
"same bug class within one shard" test (`autonomous-execution.md` Rule 4). File
as a follow-up issue, do NOT bundle.

**Revised shard plan** (split from the original single shard 1 per the
red-team exception-taxonomy finding):

| Shard           | Content                                                                                                             | Depends on      | Invariants | Why split                                                                                                                          |
| --------------- | ------------------------------------------------------------------------------------------------------------------- | --------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| **1a**          | WU-1a — `ProtectionViolation(NodeExecutionError)` re-base + CHANGELOG + `except NodeExecutionError` call-site audit | — (lands first) | 4          | Public-exception-taxonomy change + cross-package audit; distinct concern from node-override; CHANGELOG-bearing, independent review |
| **1b**          | WU-1b — `async_run` override (delete sync `run()` override) + restore 2 gap-tests, same commit                      | 1a              | 5          | Node-override wiring; gap-tests assert genuine `ProtectionViolation` through runtime — true only post-1a                           |
| **2**           | WU-3 — plain-`LocalRuntime`/`AsyncLocalRuntime` workflow-runtime Tier-2 (the red-team-finding regression guard)     | 1a + 1b         | — (test)   | Exercises the `execute_async` re-raise path; would fail P1-only                                                                    |
| **3**           | WU-4 — per-mutation-surface Tier-2 matrix (3-way shardable: write-block / read-allow / model+field)                 | 1b              | — (test)   | Boilerplate scales; parallel with shard 2                                                                                          |
| **(follow-up)** | WU-5 — delete dead `AsyncSQLProtectionWrapper`                                                                      | —               | —          | Separate bug class, exceeds same-shard budget; filed as follow-up issue, NOT bundled                                               |

Revised shard count: **4 shards** (1a, 1b, 2, 3) + 1 follow-up issue
(WU-5) — was 3 shards + 1 follow-up before the red-team split. 1a must
precede 1b (dependency). 2 and 3 may run in parallel after 1b. All
shards have live test feedback loops. The ≤3-parallel-wave cap
(`worktree-isolation.md` Rule 4) is not binding here — 1a→1b is
sequential by dependency, and only {2, 3} are parallelizable (a wave
of 2).

---

## 4. Risks

### R1 — Protection now fires where it silently didn't (this is the fix, by design)

Every write that a `read_only`/`production_safe`/model/field/business-hours
config was _supposed_ to block will now actually raise `ProtectionViolation`.
Code that "worked" only because protection was a no-op will now fail. **This is
correct** — it is a security fix; blocking-where-it-should-block is the intended
behavior change. It MUST be called out prominently in the CHANGELOG as a
behavior change (a user relying on the broken state — e.g. running writes
against a `production_safe`-configured prod DB that silently let them through —
will now correctly get blocked). This is not a regression to mitigate; it is
the defect being closed. No deprecation shim is appropriate for a security
no-op being made real (`zero-tolerance.md` Rule 2 — a fake safety gate made
real is not a "removal").

### R2 — Read/list/count MUST NOT be blocked by a write-protection check (HIGH — verify)

`check_operation` maps `read`/`list`→`OperationType.READ` and
`count`→`OperationType.READ` (`protection.py:295`,`:323`,
`_operation_mapping`). The default configs allow READ:
`read_only_global` allows `{READ}` (`protection.py:243-248`),
`production_safe` allows `{READ}` (`protection.py:271-282`),
`business_hours` allows `{READ}` (`protection.py:251-268`). So with `self.operation
∈ {read,list,count}`, the global/connection checks pass and the op is NOT
blocked — correct. **BUT**: `count`'s node operation string must be exactly
`"count"`. Verified: `nodes.py:638` sets `self.operation = operation` and the
count node is created with `operation="count"` (`nodes.py:426-427`). The
former class-name parser only recognized `Read`/`List` (mapping `Count`→
`unknown`→`CUSTOM_QUERY`, which `production_safe`/`read_only` do NOT allow → a
_spurious block on count_). The recommended design's `self.operation` read
fixes this latent bug. WU-4 MUST include explicit "read/list/count NOT blocked
under read-only" assertions to pin this and prevent a future regression where a
read path accidentally raises.

### R3 — Bulk operation strings

`self.operation` for bulk nodes is `bulk_create` / `bulk_update` /
`bulk_delete` / `bulk_upsert` (node names generated at `nodes.py:465-477`).
These map exactly via `_operation_mapping` (`protection.py:296-299`). The old
class-name parser did NOT handle these (its if-ladder stopped at
Create/Update/Delete/Read/List → `unknown`). The `self.operation` design is
strictly more correct. No risk, but WU-4 must cover all four bulk surfaces
because they were _never_ enforced before (worse orphan than single-record).

### R4 — `dataflow_instance` not yet bound

If any path reaches `async_run` before `dataflow_instance` is set, the
`hasattr` guard (carried over from the sync override) makes the check a no-op
(fail-open). Express always binds it (`express.py:225`) and the workflow
generator binds it (`nodes.py:639`), so in practice it is always present. This
is a pre-existing fail-open posture inherited verbatim from the sync override —
NOT introduced by this fix. Flag for the reviewer: consider whether a missing
`_protection_engine` on a `ProtectedDataFlow` should fail-closed instead; out
of scope for the orphan fix but worth a follow-up note.

### R5 — `upsert_advanced` / file-import surfaces

`upsert_advanced` (`express.py:1312`) and the file-import path
(`express.py:1886`/`2311`) also call `async_run`. P1 covers them automatically
(same `ProtectedNode.async_run`). No extra work, but WU-4 should include at
least an `upsert` assertion since upsert was in the never-enforced set.

### R6 — `AsyncSQLProtectionWrapper` left dead

Not deleting it in this PR leaves a known orphan (`orphan-detection.md` §3
prefers deletion). Mitigation: WU-5 files the follow-up explicitly so it is
tracked, not silently abandoned. Acceptable because deleting it is a different
bug class and exceeds the security-fix shard budget.

### R7 — Public-exception-taxonomy change (Option (a)) — downstream behavior change (MEDIUM)

Re-basing `ProtectionViolation` onto `NodeExecutionError` means any
downstream user code with `except NodeExecutionError` will now ALSO
catch `ProtectionViolation` (previously it escaped that handler as a
bare `Exception` subclass). This is a real behavior change for
downstream consumers, NOT internal-only. It is the _correct_ taxonomy (a
policy block IS a node-execution failure) but it MUST land with a
CHANGELOG entry documenting: (1) the base-class change, (2) the
precedence pattern — downstream code that wants to special-case
"blocked by policy" adds `except ProtectionViolation` BEFORE its
`except NodeExecutionError` (MRO ordering). Per
`zero-tolerance.md` Rule 6a this is NOT a removal needing a deprecation
shim (no symbol removed; a base class widened) — but it IS a documented
public-surface change. Severity MEDIUM: silent for the common case
(callers catching `ProtectionViolation` or `Exception` are unaffected;
only `except NodeExecutionError` callers see the new catch), loud via
CHANGELOG. WU-1a owns the CHANGELOG entry.

### R8 — I9 (audit-record-on-block) is satisfied by routing through `check_operation` (LOW)

Spec invariant I9 (added this revision) requires every blocked op to
emit an auditable record before the raise. `_handle_violation`
(`protection.py:414-425`) calls `auditor.log_violation` (`:418`) +
`logger.warning` (`:205`) BEFORE the `raise` (`:421`). P1 calls
`check_operation` (which calls `_handle_violation`) — so I9 is satisfied
automatically by the recommended design, NO extra work. The risk is
only realized if a future refactor bypasses `check_operation` with a
hand-rolled level check (which I9's spec text now explicitly forbids).
WU-4's model/field enforcement test SHOULD additionally assert
`db.get_protection_audit_log()` contains the violation event after a
blocked op, pinning I9 behaviorally (not just structurally). LOW: the
behavior already exists and ships; the test is the regression guard.

---

## Appendix — primary file:line index (re-verified this session)

- `protection.py:163-181` `ProtectionViolation` (currently plain `Exception`; Option (a) re-bases to `NodeExecutionError`)
- `protection.py:418` `_handle_violation` → `auditor.log_violation` (I9 audit record, BEFORE the `:421` raise)
- `protection_middleware.py:189-191` `get_protection_audit_log()` (I9 operator-readable surface)
- `protection.py:290-300` `_operation_mapping`
- `protection.py:302-392` `check_operation`
- `protection.py:414-425` `_handle_violation` (raises BLOCK/AUDIT, logs WARN)
- `protection.py:237-282` `read_only_global` / `business_hours` / `production_safe` (all allow READ)
- `protection_middleware.py:279-391` `protect_dataflow_node` / `ProtectedNode`
- `protection_middleware.py:294-385` sync `run()` override (TO BE REMOVED)
- `protection_middleware.py:351-372` context build + `check_operation` call (pattern to port to `async_run`)
- `protection_middleware.py:394-451` `AsyncSQLProtectionWrapper` (dead; follow-up)
- `protection_middleware.py:50-98` `ProtectedDataFlowRuntime.execute` results-scan re-raise
- `protected_engine.py:35-48` `ProtectedNodeGenerator._create_node_class` (applies decorator)
- `protected_engine.py:126-161` `ProtectedDataFlow.model()` (applies decorator)
- `nodes.py:498` `class DataFlowNode(AsyncNode)`
- `nodes.py:634-648` `DataFlowNode.__init__` (sets `model_name`,`operation`,`dataflow_instance`,`model_fields`)
- `nodes.py:1459-1470` `DataFlowNode.run` (sync `async_safe_run` bridge)
- `nodes.py:1472` `DataFlowNode.async_run`
- `base_async.py:98-145` `AsyncNode.execute` (never calls `run()`)
- `base_async.py:180-192` `AsyncNode.run` (raises NotImplementedError)
- `base_async.py:214-282` `AsyncNode.execute_async` (`await self.async_run` at :260; re-raise allowlist `except NodeValidationError` :271-273 / `except NodeExecutionError` :274-276; `except Exception` WRAPS in `NodeExecutionError` :277-282 — the red-team finding)
- `local.py:4236-4242` std dispatch prefers `execute_async`
- `local.py:3137-3140` async-runtime dispatch prefers `execute_async`
- `express.py:213-226` `_create_node` (binds `dataflow_instance` at :225)
- `express.py:344-373` `_trust_check_read`/`_trust_check_write` (Express-hook precedent)
- `express.py:621-628` create exception handling (raises, does NOT swallow)
- `express.py:751-779` read exception handling (not-found→None; ProtectionViolation→raise)
- `express.py` async_run call sites: 623,730,808,894,1000,1096,1170,1233,1312,1377,1505,1584,1886,2311
- `tests/unit/test_protection_system_critical_gaps.py:316-405` / `:407-455` — the 2 intent-changed tests with `# KNOWN COVERAGE GAP — tracked: issue #1050` markers
