# Static Analysis Baseline — engine.py

**Domain:** Static analysis (pyright) coverage of `packages/kailash-dataflow/src/dataflow/core/engine.py`
**Authority:** This spec captures the diagnostic baseline as it ships on `main @ a28caf0d` (2026-05-04). Per `rules/spec-accuracy.md` Rule 5, this content describes what exists TODAY, not what the cleanup intends to achieve.

## File under audit

| Property       | Value                                                   |
| -------------- | ------------------------------------------------------- |
| Path           | `packages/kailash-dataflow/src/dataflow/core/engine.py` |
| LOC            | 10,393                                                  |
| Top-level defs | 2 (1 class, 1 helper)                                   |
| Last modified  | `9680569f wip(711): wire db.transactions_sync property` |

## Verifying command

```bash
cd /Users/esperie/repos/loom/kailash-py
uv run pyright packages/kailash-dataflow/src/dataflow/core/engine.py
```

## Current errors (5)

| #   | Line | Diagnostic                                                   | Rule code                     |
| --- | ---: | ------------------------------------------------------------ | ----------------------------- |
| E1  | 3437 | `Import "tests.fixtures.mock_helpers" could not be resolved` | reportMissingImports          |
| E2  | 3789 | `"TenantContextSwitch" is not defined`                       | reportUndefinedVariable       |
| E3  | 4481 | `"discovered_schema" is possibly unbound`                    | reportPossiblyUnboundVariable |
| E4  | 4496 | `"asyncio" is possibly unbound`                              | reportPossiblyUnboundVariable |
| E5  | 4504 | `"asyncio" is possibly unbound`                              | reportPossiblyUnboundVariable |

## Current warnings (56)

Grouped by failure class. Per-warning detail enumerated in `01-analysis/01-research/02-warning-categorization.md`.

| Class | Count | Failure shape                                                                  |
| ----- | ----: | ------------------------------------------------------------------------------ |
| W1    |    12 | `build_connection_string` Optional args (`Any \| None` → required `str`/`int`) |
| W2    |    13 | Optional member access on lazily-initialized backing objects                   |
| W3    |    10 | `None` assigned to typed parameter (non-`build_connection_string` sites)       |
| W4    |     5 | `type[Node]` attribute access                                                  |
| W5    |     4 | Dynamic class-attribute writes (`type[_]._dataflow`, `_dataflow_meta`)         |
| W6    |     2 | `with cursor:` against async-only Cursor type                                  |
| W7    |    10 | Misc one-offs                                                                  |

## SHA-grounding

All 5 errors AND all 56 warnings pre-date the issue #781 cleanup cycle. Grounded per `rules/zero-tolerance.md` Rule 1c:

```bash
git log --oneline packages/kailash-dataflow/src/dataflow/core/engine.py | head -3
# 9680569f wip(711): wire db.transactions_sync property + close hooks
# aa2adbec chore: scrub external app references from public-facing surfaces
# 8dc0cd3d fix(dataflow): DDL batches use one sync connection (MED-S6 of #714)
```

The L3437 error specifically traces to the v0.7.0+ shim documented at L3431-3433 ("MockConnectionPool has been moved to tests.fixtures.mock_helpers") — the shim has shipped this way since the v0.7.0 migration commit, per the in-file docstring.

## Public surface invariant

Per brief acceptance criterion #5, the cleanup MUST NOT change the public API surface. The following symbols are PUBLIC contracts that the cleanup preserves:

- `DataFlow.discover_schema(use_real_inspection: bool = True) -> Dict[str, Any]` — return type unchanged
- `DataFlow.tenant_context` property → `TenantContextSwitch` — return type unchanged
- `DataFlow._connection_pool` (legacy attribute, used by the `MockConnectionPool` shim path) — public consumers, if any, surface in the deletion-shard's pre-flight grep

If a fix requires changing a public signature, it MUST be documented as a deviation per `rules/specs-authority.md` Rule 6 in `journal/` and surfaced for human approval at the structural-gate boundary.

## Out of scope

- Other DataFlow files (`pool_lightweight.py`, `adapters/postgresql.py`, etc.) with their own pyright drift.
- `engine.py` LOC reduction (separate `refactor-invariants.md` workstream).
- Pyright config tightening (`strict=true`, etc.) — out of this workspace's scope.
