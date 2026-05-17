# DataFlow Write Protection — Domain Spec

Authority for `ProtectedDataFlow` write-protection enforcement. Covers
what the protection contract promises, which execution paths MUST enforce
it, and the invariants the enforcement point must hold.

Source-of-truth code (referenced, not restated — `specs-authority.md` §9):
`packages/kailash-dataflow/src/dataflow/core/protection.py`,
`protection_middleware.py`, `protected_engine.py`.

## 1. What `ProtectedDataFlow` promises

`ProtectedDataFlow` is a `DataFlow` subclass that adds configurable
write-protection. Operators enable it to prevent writes:

- `enable_read_only_mode()` — block all mutations globally; allow READ.
- `production_safe` config — allow READ, block destructive mutations.
- `business_hours` config — allow READ; block writes outside a window.
- `add_model_protection(model, ...)` — per-model operation restriction.
- `add_field_protection(model, field, ...)` — per-field restriction.

The promise: **when a protection config blocks an operation, that
operation MUST raise `ProtectionViolation` instead of mutating the
database** — on every path a real user exercises. WARN-level configs log
and allow (do not raise); BLOCK/AUDIT-level configs raise.

The protection engine (`WriteProtectionEngine.check_operation`,
`protection.py:302-392`) maps an operation string → `OperationType`
(`protection.py:290-300`: create/read/update/delete/list/count/upsert/
bulk\_\*), evaluates global → connection → model → field rules, and
delegates a block to `_handle_violation` (`protection.py:414-425`) which
raises for BLOCK/AUDIT.

## 2. Paths that MUST enforce (the contract surface)

Protection MUST be enforced on ALL of:

1. **Express path** — `db.express.create/read/update/delete/list/count/
upsert/bulk_*` (the documented "23x faster" default). Each Express
   mutation calls `await node.async_run(**data)` directly.
2. **Workflow-runtime path** — `runtime.execute(workflow.build())` /
   `AsyncLocalRuntime.execute_workflow_async(...)` executing generated
   `*CreateNode` / `*UpdateNode` / etc. nodes. The runtime dispatches
   nodes via `execute_async` → `async_run`.
3. **Raw node path** — direct `node.async_run(**kwargs)` /
   `node.execute(...)` callers (sync `execute` reroutes through
   `AsyncNode.execute_async` → `async_run`).

All three converge on `DataFlowNode.async_run()`. That convergence point
is the contract's single enforceable chokepoint.

## 3. Enforcement-point invariants

The enforcement point (the method that invokes `check_operation`) MUST:

- **I1 — Single-check.** Exactly one `check_operation` call per logical
  user operation. No double-check (sync `run()` → `async_run()` must not
  check twice).
- **I2 — Pre-I/O.** The check runs BEFORE table-existence DDL and BEFORE
  any connection-pool acquisition. A blocked write never takes a
  connection.
- **I3 — Exact operation string.** The operation passed to
  `check_operation` MUST be the canonical `self.operation`
  (`create`/`read`/.../`bulk_upsert`), NOT a class-name parse. Class-name
  parsing mis-maps `upsert`/`count`/`bulk_*` and both over-blocks
  (`count` under read-only) and under-blocks (bulk never enforced).
- **I4 — Model/field reachability.** `model_name` MUST reach
  `check_operation` so `add_model_protection` / `add_field_protection`
  enforce. An SQL-string-layer check that loses `model_name` does NOT
  satisfy the contract.
- **I5 — Raise, not swallow.** A raised `ProtectionViolation` MUST
  propagate to the caller — Express MUST surface it as an exception, not
  fold it into a result dict; `read()`'s not-found→`None` filter MUST NOT
  absorb it (its message contains "protection blocks", not "not found").
- **I6 — WARN semantics preserved.** A WARN-level config logs and
  ALLOWS; only BLOCK/AUDIT raise. The enforcement point must not raise on
  WARN.
- **I7 — READ never write-blocked.** `read`/`list`/`count` map to
  `OperationType.READ`; the default read-only / production-safe /
  business-hours configs ALL allow READ. These ops MUST NOT raise under a
  write-protection config.
- **I8 — Instance isolation.** Enforcement MUST NOT globally monkeypatch
  a shared node class (process-wide mutation contaminates unprotected
  DataFlow instances in the same process).
- **I9 — Block emits an auditable record.** Every blocked operation MUST
  emit an audit record before the raise — the security signal an
  operator monitors. `_handle_violation` (`protection.py:414-425`) calls
  `self.config.auditor.log_violation(violation, context)` (`:418`) which
  appends to `ProtectionAuditor.events` (`:204`) AND emits
  `logger.warning("protection.protection_violation", ...)` (`:205`)
  BEFORE the `raise` (`:421`). Reachable via
  `db.get_protection_audit_log()` (`protection_middleware.py:189-191`).
  The enforcement point MUST route blocks through `_handle_violation`
  (i.e. call `check_operation`, not a hand-rolled level check) so this
  record is emitted on every blocked path. A WARN-level config logs the
  same record and does NOT raise (I6).

## 4. Current conformance

`check_operation` is invoked only from synchronous call sites
(`protection_middleware.py:367` in `ProtectedNode.run()`; `:422` in
`AsyncSQLProtectionWrapper`'s sync closure). `ProtectedNode`
(`protect_dataflow_node()`) overrides only synchronous `run()`. All three
§2 paths dispatch through `AsyncNode.execute_async` → `async_run`, which
`ProtectedNode` does not override — so enforcement of §1's promise does
not currently reach those paths. Tracked: issue #1050. Root-cause
evidence (independent 2-agent verification) and the fix design /
acceptance criteria are workstream artifacts, not spec content — see
`workspaces/issue-1050-protection-orphan-async/` (`01-analysis/`,
`02-plans/`). This spec describes the contract (§1–3) the fix must
satisfy; it is updated to "enforced on all §2 paths" when that lands on
`main` (per `specs-authority.md` §5).
