# 02 — Spec Mapping

Per `/analyze` Step 5, every requirement sentence in `briefs/` MUST map to a corresponding spec file section. This file is the traceability matrix.

## Existing spec authority

The kailash-py SDK already has spec coverage for both packages this workstream touches:

| Spec file                   | Authority over                                                      |
| --------------------------- | ------------------------------------------------------------------- |
| `specs/dataflow-core.md`    | DataFlow class, constructor, `auto_migrate`, engine, exceptions     |
| `specs/dataflow-cache.md`   | Cache layer, **dialect, record ID coercion, transactions, pooling** |
| `specs/dataflow-express.md` | Express API surface                                                 |
| `specs/dataflow-models.md`  | `@db.model` decorator semantics                                     |
| `specs/core-nodes.md`       | AsyncSQLDatabaseNode contract (within Core SDK)                     |

No NEW spec file is needed. The fix is updating sections in TWO existing specs:

## Spec gap 1 — `specs/dataflow-core.md`

**Current state:** likely has an `auto_migrate` section but treats it as a boolean flag.

**Required addition:** semantic specification of `auto_migrate` enum with three values:

- `True` (default): fail-fast on first failed DDL with `DDLFailedError`; subsequent accesses re-raise; operator must override or fix.
- `"warn"`: log + continue (current behavior, opt-in for legacy apps).
- `False`: no auto-migration; operator manages migrations explicitly.

**Required addition:** explicit specification that `_failed_table_creations` is a public-but-frozen attribute readable for diagnostic purposes (`db._failed_table_creations` enumerable for support scripts).

**Required addition:** the invariant that a failed DDL fires exactly ONE log line + ONE metric increment, NOT N per request.

## Spec gap 2 — `specs/dataflow-cache.md`

**Current state:** likely covers dialect + transactions + pooling but at the DataFlow layer, not the underlying `AsyncSQLDatabaseNode`.

**Required addition (for #697 + #698):** AsyncSQLDatabaseNode pool lifecycle contract:

- Pool lifecycle states: `created → active → idle → reaped`.
- `_PROCESS_POOL_REGISTRY` is the single ground truth for pool count; `pool_count()` enumerates.
- `idle_timeout` default: 300 s; configurable via `set_pool_defaults()`.
- `max_pool_count_per_process` default: 100; configurable via `set_pool_defaults()`.
- `PoolExhaustedError` semantics — typed error raised when cap is reached; caller chooses to wait, retry, or raise.
- The fallback path is bounded — under cap, fallback creates pool + registers; over cap, fallback fails-fast.

**Required addition:** the invariant that pools created in fallback mode are tracked + reapable, identical to pools created via the runtime-managed path.

**Required addition (cross-SDK alignment):** Note that `kailash-rs`'s pool lifecycle MUST match this contract semantically (per `rules/cross-sdk-inspection.md` § 3 EATP D6).

## Spec gap 3 — `specs/dataflow-core.md` (DataFlowEngine section)

**Current state:** likely has a DataFlowEngine section that documents `register_model(registry, model)`.

**Required addition (for #685):** explicit cross-reference that `DataFlow.register_model(model_cls)` is the underlying mechanism + that `@db.model` is sugar over the same path. Both produce identical state.

**Required addition (for #686):** `DataFlowEngineBuilder.build()` is async-by-signature for cross-SDK parity but body is sync in kailash-py; `build_sync()` is the documented Python escape hatch for module-import-time patterns.

## Brief traceability check

Each requirement sentence in `briefs/01-incident-context.md` maps to a spec section:

| Brief requirement                                                                            | Spec section                                          |
| -------------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| "DDL failures fail-fast at startup with typed error + bounded retry"                         | `dataflow-core.md` § auto_migrate semantics           |
| "AsyncSQLDatabaseNode pool fallback either holds longer / fails-fast OR registers"           | `dataflow-cache.md` § pool lifecycle contract         |
| "idle-timeout + LRU cap configurable on EnterpriseConnectionPool"                            | `dataflow-cache.md` § pool lifecycle contract         |
| "DataFlowEngine.register_model is either implemented end-to-end or removed"                  | `dataflow-core.md` § DataFlowEngine.register_model    |
| "DataFlowEngineBuilder.build() either gains a sync companion or honours its async signature" | `dataflow-core.md` § DataFlowEngine.builder           |
| "Tier-2 regression tests for every fix"                                                      | `dataflow-core.md` § conformance / `rules/testing.md` |
| "Cross-SDK inspection on every fix"                                                          | `rules/cross-sdk-inspection.md` § 1 + EATP D6         |

ALL brief requirements have a spec home. No orphan requirements.

## What this means for /implement

Spec updates land in the SAME PR as the source code changes — per `rules/specs-authority.md`. Each shard's PR includes:

- Source code fix
- Spec section update
- Tier-2 regression test
- CHANGELOG entry

This avoids the "spec drift behind code" failure mode that issue #693 tracks for ML.

## Out-of-scope spec gaps

The following are spec-level questions worth flagging but NOT blocking this workstream:

- **`specs/dataflow-cache.md` does not currently spec `EnterpriseConnectionPool` as a manager-shape class** — per `rules/facade-manager-detection.md` § 2, manager classes need named Tier-2 wiring tests. The pool registry test added in Shard B satisfies this implicitly but should be referenced from the spec for traceability.
- **No spec exists for the `_failed_table_creations` diagnostic surface** — adding it post-implementation is fine; the spec authoritatively reflects what shipped.
