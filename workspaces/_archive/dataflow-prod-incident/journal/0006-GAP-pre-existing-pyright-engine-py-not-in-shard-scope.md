# 0006 GAP — Pre-Existing Pyright Diagnostics On engine.py Out Of Shard Scope

**Date:** 2026-04-28
**Session:** dataflow-prod-incident /redteam
**Type:** GAP

## Finding

The IDE's pyright server surfaces ~10 type-error diagnostics on `packages/kailash-dataflow/src/dataflow/core/engine.py` that pre-date this workstream:

- Line 3404: `TenantContextSwitch` is not defined (`reportUndefinedVariable`)
- Line 4096: `discovered_schema` possibly unbound
- Line 4111, 4119: `asyncio` possibly unbound
- Line 256: `max_overflow` not a known attribute of `DataFlowConfig`
- Line 287: `enhance_invalid_database_url` not a known attribute of `None`
- Line 542, 5293: `_engine`, `get_connection` unknown attributes
- Line 5347-5371: `Any | None` arg passed to function expecting `str`/`int`
- Line 1432, 1958, 2004, 1876: optional-member-access errors

These are all on lines that pre-date the Shard A + C edits (which touched `__init__` enum + `_register_model` + `ensure_table_exists` + `_execute_ddl[_async]` + the two engine.py builder methods). None are introduced by this workstream.

## Why this is a GAP

Per `rules/zero-tolerance.md` Rule 1 ("if you found it, you own it"), strict reading mandates the agent fix every WARN+ surfaced. The shard-scope clause (autonomous-execution.md § Per-Session Capacity Budget) carves out an exception: a same-bug-class fix within the shard's invariant budget MUST be done immediately; out-of-scope pre-existing diagnostics are deferred with a tracking record.

These 10 diagnostics fall in the latter category — they are NOT same-bug-class as DDL retry storm, pool lifecycle, or engine surface. They are independent type-correctness gaps in the DataFlow engine's older code that need their own dedicated fix cycle.

## Recommended disposition

Open a follow-up issue or workspace `dataflow-engine-pyright-cleanup` to:

1. Audit each diagnostic
2. Fix the type annotations or imports (likely a 100–200 LOC cleanup)
3. Add a pyright-strict CI gate for `engine.py` to prevent regression

## What this workstream did NOT do

- Did NOT introduce new pyright errors (every new method has type annotations; `mypy --strict` was the pre-flight gate)
- Did NOT silence existing errors via `# type: ignore` (would violate `rules/observability.md` § "Silent log-level downgrades" sibling discipline)
- Did NOT extend the failure ratchet — the count is unchanged from main pre-shard

## Related

- `rules/zero-tolerance.md` Rule 1 (shard-scope clause)
- `rules/autonomous-execution.md` § Per-Session Capacity Budget
- This workstream's PR series: #702, #703, #704, #705, #706
