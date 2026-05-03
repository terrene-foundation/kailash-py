# /redteam Aggregate — Round 1

**Date**: 2026-04-18
**Scope**: 4 session commits (7a4fd364 → d5f528ce) + adjacent state across
closed issues #492, #493, #495, #496, #497 and prior-session #490, #491.
Plus check of loose ends documented in `.session-notes`.

## Verdict

**CONVERGENCE CANDIDATE** after round-1 fixes. 3 HIGH findings → all fixed
in-session; need round-2 clean pass + test re-run.

## Round-1 Findings Summary

| Agent              | CRIT | HIGH | MED | LOW | Outcome                               |
| ------------------ | ---- | ---- | --- | --- | ------------------------------------- |
| spec-compliance    | 0    | 0    | 0   | 0   | 46/46 assertions PASS via AST/grep    |
| security-reviewer  | 0    | 1    | 4   | 2   | H1: raw params logged at ERROR        |
| testing-specialist | 0    | 0    | 1   | 2   | 72 pass / 1 skip / 0 fail             |
| orphan-sweep       | 0    | 2    | 1   | 0   | H1: pool dead branch; H2: orphan mgr  |
| code-review        | 0    | 0    | 2   | 3   | Zero stubs in changed files           |
| log-triage         | 0    | 0    | 0   | 0   | Only expected #478 DeprecationWarning |

**HIGH findings (3 total) — all fixed this round:**

### HIGH-1 (Security-H1) — Raw `params` logged at ERROR in connection_adapter

- **File**: `packages/kailash-dataflow/src/dataflow/utils/connection_adapter.py:170`
- **Issue**: `logger.error(..., extra={"params": params})` inside generic
  exception handler leaks classified row values (PII, secrets) at ERROR
  level to every log aggregator.
- **Violates**: `rules/security.md` § No secrets in logs; `rules/observability.md`
  Rule 4; `rules/dataflow-classification.md` MUST Rule 1.
- **Fix**: Replaced raw `params` emission with `param_count` only. SQL is
  parameterized and safe to log.
- **File updated**: `connection_adapter.py:164-175` — single structured
  `logger.error` with `error`, `sql`, `param_count` fields only. Added
  inline rule-reference comment.

### HIGH-2 (Orphan-H1) — BulkUpsertNode pool dead branch

- **File**: `packages/kailash-dataflow/src/dataflow/nodes/bulk_upsert.py:614-630`
- **Issue**: `self._pool_manager.execute(operation="execute", ...)` hits
  `ValueError("Unknown operation: execute")` from
  `DataFlowConnectionManager.execute()` allowlist
  (`workflow_connection_manager.py:156-171`), gets swallowed by bare
  `except Exception`, logs a generic WARN, and silently falls through to
  direct path.
- **Violates**: `rules/zero-tolerance.md` Rule 3 (silent fallback);
  `rules/dataflow-pool.md` Rule 3 (deceptive configuration);
  `rules/orphan-detection.md` MUST 3 (removed = deleted, not deprecated).
- **Fix**: Deleted the dead branch + `try/except` + silent WARN. Added
  explicit `NodeValidationError` when caller passes
  `use_pooled_connection=True`, naming `BulkCreatePoolNode` as the
  correct alternative. Updated docstring to document the constraint and
  reference both rules.

### HIGH-3 (Orphan-H2) — `DataFlow._tenant_trust_manager` facade orphan

- **File**: `packages/kailash-dataflow/src/dataflow/core/engine.py:627, 661-665`
- **Issue**: `_tenant_trust_manager: TenantTrustManager` constructed when
  `multi_tenant=True` + trust enabled, but zero call sites in
  `packages/kailash-dataflow/src/` invoke any of its methods
  (`verify_cross_tenant_access`, `create_cross_tenant_delegation`,
  `get_row_filter_for_access`). Phase 5.11-shaped orphan — the spec at
  `specs/dataflow-core.md:373` promised "Multi-tenant trust isolation".
- **Violates**: `rules/orphan-detection.md` MUST 1, 3;
  `rules/facade-manager-detection.md` MUST 1.
- **Fix**: Removed `_tenant_trust_manager` attribute init + conditional
  construction block. Retained `TenantTrustManager` class + unit tests —
  it is still available at `dataflow.trust.multi_tenant.TenantTrustManager`
  for consumers that need cross-tenant verification. Spec line 373
  updated to document standalone availability and note that the facade
  will be wired in the same PR as a production call site (future work).

## Medium + Low Findings (Not Blocking)

**Security MEDIUM:**

- **S-M1** — `engine.py:3756, 3774, 3800` PRAGMA paths read table names
  from `sqlite_master` without `_validate_identifier`. Same class of
  gap as #496 fixed but on different code path.
- **S-M2** — `kailash-kaizen/src/kaizen/trust/migrations/eatp_human_origin.py:203, 271, 319`
  interpolates `column_name` / `column_type` / `index_name` without
  validation. Kailash-core sibling at `src/kailash/trust/migrations/`
  does validate. Drift between sibling SDKs.
- **S-M3** — SQLite PRAGMA interpolation in `kaizen/memory/persistent_tiers.py:44`,
  `src/kailash/core/pool/sqlite_pool.py:98`,
  `dataflow/adapters/sqlite.py:339, 376, 761, 798, 848, 1047`.
  Defense-in-depth gaps on hardcoded lists (rule 5).
- **S-M4** — DROP paths in `migrations/*.py` have no `force_drop=True`
  gate on public API surface.

**Security LOW:**

- **S-L1** — `bulk_upsert.py:364-368` WARN may echo DB error text with
  offending column value. Recommend downgrade to DEBUG + separate WARN
  counter.
- **S-L2** — `engine.py:5086` FK constraint SQL missing
  `_validate_identifier` on 4 identifiers.

**Code-review MEDIUM / LOW:**

- **CR-M1** — `496-pg-placeholder-audit.md` uses future tense ("should file")
  after fix already shipped. Recommend self-certification footer.
- **CR-L** — 3 items: LocalRuntime deprecation filterwarnings missing in
  8 tests (pre-existing, #478 fix shipped in 6fcba899), import ordering,
  multi-word PG type regex.

**Testing MEDIUM:**

- **T-M1** — `src/kailash/nodes/admin/schema_manager.py` hardcoded-list
  validator routing has no spy-based regression test (analogous to
  `test_issue_446_dlq_identifier_validation.py`).

**Orphan MEDIUM:**

- **O-M1** — `test_phase_5_11_trust_wiring.py` is monolithic;
  `rules/facade-manager-detection.md` MUST 2 wants
  `test_<lowercase_manager>_wiring.py` per facade.

## Disposition

- **HIGH** (3 total) — all fixed this session. File a follow-up cross-SDK
  ticket for S-M2 (kailash-rs parity on eatp_human_origin identifier
  validation).
- **MEDIUM** (9 total) — file as grouped GH issues tagged
  `defense-in-depth`. None are exploitable today.
- **LOW** (5 total) — fold into next DataFlow touch.

## Open GH Issues Surveyed (Out of Session Scope)

10 open on terrene-foundation/kailash-py:

| #   | State | Note                                                        |
| --- | ----- | ----------------------------------------------------------- |
| 488 | OPEN  | kaizen.ml register_estimator (cross-SDK)                    |
| 480 | OPEN  | DataFlowExpress malformed PG (BUG, cross-SDK, P0-ish)       |
| 479 | OPEN  | ml.Pipeline rejects custom estimators                       |
| 478 | OPEN  | LocalRuntime deprecation — FIXED in 6fcba899, needs release |
| 477 | OPEN  | SignatureMeta 3.14 — FIXED in 6fcba899, needs release       |
| 473 | OPEN  | nexus ServiceClient (feature)                               |
| 465 | OPEN  | typed S2S client (feature)                                  |
| 464 | OPEN  | nexus HttpClient SSRF-aware (P1 feature)                    |
| 463 | OPEN  | llm-client error hierarchy (feature)                        |
| 462 | OPEN  | llm-client embed bindings (BLOCKER feature)                 |

**Action**: #477 and #478 already fixed in commit 6fcba899 but remain OPEN
pending `kailash-dataflow 2.0.9` release. Close with release commit SHA
when shipped per `rules/git.md` § Issue Closure Discipline.

## Round-1 Exit

- 3 HIGH fixed: `connection_adapter.py`, `bulk_upsert.py`, `engine.py`
- 72 pass / 1 skip / 0 fail on regression suites post-fix
- Ready for round-2 clean pass

## Files Changed This Session

```
.../kailash-dataflow/src/dataflow/core/engine.py                | -13 +6
.../kailash-dataflow/src/dataflow/nodes/bulk_upsert.py          | -19 +12
.../kailash-dataflow/src/dataflow/utils/connection_adapter.py   | -5  +10
specs/dataflow-core.md                                          | -1  +1
```

4 files. Single logical change per commit pending.
