# DataFlow Perfection — Red Team Findings

**Date**: 2026-04-08
**Scope**: Verify executive summary, eight subsystem audits, and master fix plan against source.
**Method**: Source-level verification of top-20 damning claims + plan integrity checks.

## Verdict: PASS WITH AMENDMENTS

The audit is **substantively correct on every architectural claim**: the façade managers are real, the SQL injection sites are real, the `eval`/`exec` RCE sites are real, the cache tenant leak is real, the orphan subsystems are real, and the observability collapse is real. However, **several quantitative claims are overstated by 20-80%**, the migration-history claim is factually wrong, and the plan has **undetected dependency conflicts** between PR-1, PR-4, and PR-3, plus a **version-bump conflict** with the active `workspaces/issue-354/` plan that the master plan does not acknowledge.

The architectural verdict ("FOUNDATIONALLY BROKEN") holds. The remediation plan needs targeted amendments before `/todos`.

## Verification of top-20 claims

| #   | Claim                                                           | File:line                                                                   | Verdict      | Notes                                                                                                              |
| --- | --------------------------------------------------------------- | --------------------------------------------------------------------------- | ------------ | ------------------------------------------------------------------------------------------------------------------ |
| 1   | `TransactionManager` is a Python dict with `status="committed"` | `features/transactions.py:30-58`                                            | **VERIFIED** | Exact match. Zero DB interaction, pure dict manipulation.                                                          |
| 2   | `TransactionManager` instantiated line 453, exposed line 2825   | `core/engine.py:453` / `:2825`                                              | **VERIFIED** | Line 453 and 2825 exactly as claimed.                                                                              |
| 3   | `ConnectionManager` returns hardcoded dicts                     | `utils/connection.py:77,93,131`                                             | **VERIFIED** | Lines 77, 93, 131 contain "In real implementation, would..." verbatim.                                             |
| 4   | `MultiTenantManager` hardcodes `"created_at": "2024-01-01..."`  | `features/multi_tenant.py:28`                                               | **VERIFIED** | Exact match at line 28.                                                                                            |
| 5   | `encrypt_tenant_data` is `f"encrypted_{key}_{data}"`            | `core/multi_tenancy.py:925-939`                                             | **VERIFIED** | Line 936 exact. Bare `except: pass` at 930-932 also verified.                                                      |
| 6   | 13 SQL f-string injection sites in multi_tenancy                | `core/multi_tenancy.py:334,367,415,420,424,427,429,452,456,477,482,490,494` | **VERIFIED** | All 13 sites exist and f-string interpolate `tenant_id` / `schema_name`.                                           |
| 7   | `eval(row["embedding"])` in semantic search                     | `semantic/search.py:134`                                                    | **VERIFIED** | Exact line match.                                                                                                  |
| 8   | `exec(self.filter_code, ...)` in dynamic_update                 | `nodes/dynamic_update.py:172,182`                                           | **VERIFIED** | Both lines exact.                                                                                                  |
| 9   | `UpdateNode` `field_names = list(updates.keys())` no whitelist  | `core/nodes.py:2192,2195,2235,2248`                                         | **VERIFIED** | Exact match. No whitelist against `model_fields`. All three dialects.                                              |
| 10  | `generate_express_key` has no tenant dimension                  | `cache/key_generator.py:97-135`                                             | **VERIFIED** | Zero `tenant` / `tenant_id` references in function.                                                                |
| 10b | `features/express.py` call sites never pass tenant_id           | `features/express.py:964,988`                                               | **VERIFIED** | `generate_express_key(model, operation, params)` — no tenant arg.                                                  |
| 11  | `auto_migrate(interactive=False, auto_confirm=True)` + swallow  | `core/engine.py:5191-5196,5209-5212`                                        | **VERIFIED** | Both ranges exact. Comment "Don't fail model registration" at 5211.                                                |
| 12  | `migration_history.jsonl` has 44 runs all `success: false`      | `migrations/performance_data/migration_history.jsonl`                       | **WRONG**    | 44 lines total but **28 are `success: true`**, only 16 `false`.                                                    |
| 13  | `pytest.ini:34 --disable-warnings -p no:warnings`               | `pytest.ini:40-41`                                                          | **PARTIAL**  | Correct content, wrong line numbers (40-41, not 34).                                                               |
| 14  | `dataflow/__init__.py:92 suppress_core_sdk_warnings()`          | `dataflow/__init__.py:92`                                                   | **VERIFIED** | Exact line.                                                                                                        |
| 15  | CLI commands print "coming soon"                                | `cli/main.py:42,83,112,125,137,146`                                         | **VERIFIED** | `init` prints "coming soon..." + `# Mock the DataFlow instantiation for testing` comment at line 37.               |
| 16  | `dataflow/trust/` is 2,407 LOC with zero production importers   | `dataflow/trust/*.py`                                                       | **VERIFIED** | Exactly 2,407 LOC. Only importers: self-references + `docs/` + tests.                                              |
| 17  | 969 f-string logger calls across 99 files                       | Package-wide grep                                                           | **VERIFIED** | Exact match: 969 / 99.                                                                                             |
| 18  | 301 `print()` calls in 37 files                                 | Package-wide grep                                                           | **PARTIAL**  | Actual: **294 prints in 36 files** (using `\bprint\(`). Audit ~2% high.                                            |
| 19  | 118 mock violations in Tier 2 across 30 integration files       | `tests/integration/**`                                                      | **PARTIAL**  | Actual integration: **67 in 30 files**; e2e: 22 in 4 files. **89 / 34**. Audit overstates violation count by ~33%. |
| 20  | `compatibility/legacy_support.py:75` instantiates `Mock()`      | `compatibility/legacy_support.py:79`                                        | **PARTIAL**  | Correct pattern (`Mock()` in prod), wrong line (79, not 75).                                                       |

## Claims that FAILED verification

### Claim 12 — `migration_history.jsonl` "all 44 success:false"

Actual state: 44 total rows, **28 success=true, 16 success=false**. The 16 failures do contain `"syntax error at or near \"WHERE\""` — that part is real and damning — but the executive summary's phrasing "every single one showing success: false" is factually false. The audit's rhetorical escalation ("runtime telemetry committed to source showing the auto-migrate generator itself has been emitting broken SQL") is only true for **16/44 = 36%** of runs.

**Severity impact**: The underlying finding — that the auto-migrate generator has been producing broken SQL, that 16 failed runs were committed to source as telemetry, and that `rules/schema-migration.md` is violated — remains HIGH. But the "44/44 broken" framing cannot be used to justify the plan as written. The CRITICAL rating for Finding #15 in the exec summary is still appropriate because (a) auto_confirm=True runs DDL unreviewed on first boot, (b) failure swallowing silences telemetry, and (c) 16 historical SQL-generator bugs are 16 too many for a production feature. But the plan's language must be corrected.

## Claims that UNDERSTATED severity

### U1 — The plan treats PR-3 orphan deletion as safely parallelizable; it is not

The plan's PR-3 deletes `dataflow/semantic/` as an orphan. Verified fact: `dataflow/nodes/semantic_memory.py:17-19` imports `from ..semantic.embeddings`, `from ..semantic.memory`, `from ..semantic.search`. Deleting `semantic/` without ALSO deleting `nodes/semantic_memory.py` produces an `ImportError` on the next `dataflow` import. The plan lists semantic deletion but not semantic_memory.py. This is a **build-break waiting to happen**.

Similarly, `dataflow/compatibility/migration_path.py:107,171` imports `from dataflow.compatibility.legacy_support`. Deleting `legacy_support.py` without also deleting `migration_path.py` is a break.

`dataflow/platform/errors.py::ErrorEnhancer` is imported by `core/nodes.py:52` at runtime (lazy import). But `core/error_enhancer.py` is a **parallel ErrorEnhancer implementation** that the plan never mentions. Either (a) core/nodes.py is redirected to `core.error_enhancer` and `platform/errors.py` is deleted, or (b) `core/error_enhancer.py` is itself a dead orphan that should also be on the deletion list. The plan picks neither.

**Escalation**: `rules/zero-tolerance.md` Rule 2 — stubs AND parallel implementations. The plan needs an explicit dependency table for every deletion, or PR-3 will break `main`.

### U2 — `validate_queries=False` default

Audit mentions "hardcoded in 40+ DML call sites" as a single bullet under Finding #8. This is actually a **package-wide silent-success anti-pattern**: the core SDK provides query validation; DataFlow disables it everywhere. Combined with finding #7 (`UpdateNode` field-whitelist absence) and finding #8 (table_name f-strings), this means **DataFlow is the one SDK feature that deliberately turns off the validation its own rules mandate**. This deserves its own CRITICAL severity line, not a bullet inside another finding.

### U3 — `issue-354` plan integration

The exec summary mentions `workspaces/issue-354/` five times as "first-pass" work to integrate. The master plan's PR-6 says "integrates issue-354 plan". Verified fact: issue-354 is a **live plan targeting `1.8.0 → 1.9.0`, one cycle, one PR, branch `fix/354-fabric-redis-cache`**. The perfection plan targets `1.8.0 → 2.0.0`, 14 PRs, branch `fix/dataflow-perfection`. The two plans are **simultaneously active on the same files** (`fabric/pipeline.py`, `fabric/runtime.py`, `fabric/serving.py`, `fabric/health.py`, `fabric/products.py`, `fabric/metrics.py`, `core/engine.py`, `dataflow/__init__.py`, `pyproject.toml`, `README.md`). If issue-354 ships first, PR-6 of the perfection plan rebases onto a different set of assumptions and the CHANGELOG carries 1.9.0 + 2.0.0 notes. This is **undetected scope overlap** — severity understated from HIGH to CRITICAL.

## Claims that OVERSTATED severity

### O1 — Claim 12 (migration history all broken)

Audit: CRITICAL, framed as "every single one showing success: false". Actual: 16/44 failed = ~36% failure rate. Severity still justifies auto-migrate safety work but **not** the "generator has been broken forever" framing. Recommend re-classification: Finding #15 stays CRITICAL (auto_confirm + swallow) but the historical-evidence sub-claim is reduced to MEDIUM ("16 historical failures committed to source without remediation").

### O2 — 118 mock violations / 301 prints

Audit: 118 and 301, both CRITICAL/HIGH. Actual: 89 integration+e2e mocks and 294 prints. These are still MASSIVE violations — the reclassification does not change severity — but the exact counts cited in the plan's exit criteria will cause PR-11 and PR-0 to fail their own grep guards. Exit criteria must use "actual count → 0", not "remove 118 → 0".

## New findings the auditors missed

### N1 — PR-3 deletion list omits dependent files (BUILD BREAK CRITICAL)

`nodes/semantic_memory.py` imports `..semantic.embeddings/memory/search`. `compatibility/migration_path.py` imports `.legacy_support`. `debug/debug_agent.py`, `debug/context_analyzer.py`, `cli/analyze.py`, `cli/inspector_cli.py`, `cli/debug.py`, `cli/validate.py`, `cli/generate.py` import `platform.inspector`. If PR-3 deletes `platform/` "except Inspector + ErrorEnhancer", and keeps cli/inspector_cli.py, the import tree is okay; if PR-3 also deletes `debug/` (per the plan's Deliverables → debug/DebugAgent/ErrorCategorizer/PatternRecognitionEngine in the class-deletion list), the cli/debug.py import of `platform.inspector` still works but anything that imported from the deleted debug/ classes breaks. **Fix**: every PR-3 deletion entry MUST name every dependent file that must be deleted or redirected in the same commit.

### N2 — `core/error_enhancer.py` vs `platform/errors.py::ErrorEnhancer` (dual implementations)

Audit identified "two `DataFlowError`", "two `HealthStatus`", "two `RetentionPolicy`" as Pattern E. Missed: there are **two `ErrorEnhancer` classes** — `core/error_enhancer.py` and `platform/errors.py`. `core/nodes.py:52` imports from `platform.errors` with a lazy import explaining "circular dependency". The circular is itself evidence of the dual impl. Severity: HIGH — same pattern the audit already categorized.

### N3 — `pyproject.toml` version string mismatch

Verified fact: `dataflow/__init__.py:95` reports `__version__ = "1.7.1"`, not 1.8.0. The exec summary and master plan both claim current version is 1.8.0. Either the version is 1.7.1 (in which case the plan's baseline is wrong) or the pyproject.toml says 1.8.0 and `__init__.py` was never updated (a direct `rules/zero-tolerance.md` Rule 5 violation — "ALL version locations updated atomically"). Either way, **version consistency is broken today** and is not in the plan. Severity: HIGH.

### N4 — `InMemoryCache.invalidate_model` substring bug also affects the plan's consolidation target

The plan's PR-5 deliverable 3 says "substring `in` match in `InMemoryCache` replaced with exact key pattern match". Verified: `invalidate_model` is called at `features/express.py:991-996` via a pattern like `dataflow:v1:{model}:*`. The plan fixes the substring bug and the prefix bug but **does not audit every other `clear_pattern` / `delete_pattern` caller**. If another subsystem emulates the same bug (and given Pattern E, this is likely), the fix covers one of N sites. Severity: MEDIUM — needs cross-cache search added to PR-5.

### N5 — `suppress_warnings` is imported, not just called

`dataflow/__init__.py:82-89` imports SIX symbols from `suppress_warnings`: `configure_dataflow_logging`, `dataflow_logging_context`, `get_dataflow_logger`, `is_logging_configured`, `restore_dataflow_logging`, `suppress_core_sdk_warnings`. The plan's PR-0 deliverable 2 says "delete suppress_warnings.py and its invocation at `dataflow/__init__.py:92`". Verified: deleting the file breaks 6 imports, not 1. Every caller of these helpers must be tracked and redirected. Severity: HIGH — scope understated.

### N6 — The `no_mocking_policy` fixture at `conftest.py:455` is live but never referenced (confirmed dead)

Verified: grep returns one file (conftest.py itself). Dead policy enforcement code. PR-13 rule extension #4 says "enforce `no_mocking_policy` fixture on Tier 2/3" but doesn't say HOW. The autouse enforcement strategy needs concrete implementation — simply declaring the fixture is not enough if pytest isn't told to use it. Severity: MEDIUM.

### N7 — PR-0 deliverable 3 grep guard is too narrow

The plan says: `grep -rn '^\s*print(' src/dataflow/` must return zero. Actual prints use a mix of patterns including inline and expressions (`sys.stderr.write` equivalents). The correct guard is `\bprint\(`. Count rises from 165 to 294. Severity: MEDIUM — affects exit criteria, not architecture.

### N8 — Issue-354 plan targets `FabricTenantRequiredError` which PR-5 also introduces

Both plans define `FabricTenantRequiredError`. If issue-354 ships first, PR-5 finds the class already defined. If they land in reverse order, issue-354 PR fails code review for reintroducing a class. Severity: HIGH — merge conflict already baked in.

### N9 — Every adapter has its own `quote_identifier` pathway but the plan assumes one canonical

Per audit, `adapters/sql_dialects.py` has `quote_identifier()`. Verified. But `sql/dialects.py` is a parallel dialect module with DIFFERENT method signatures. PR-1 (security fixes) deliverable 1 says "using the canonical `quote_identifier()` helper (from PR-4) for DDL". **PR-1 depends on PR-4 for the canonical helper**, but PR-4 depends on PR-3 (dead dialect systems deleted), which depends on PR-1 (security fixes landed on live path). **This is a three-way cyclic dependency** that the plan's sequencing table does not resolve. The plan says "PR-1 → PR-3 → PR-4". But PR-1 needs PR-4's canonical helper. The only way out is a stopgap helper in PR-1 that PR-4 later promotes — the plan doesn't say this explicitly. Severity: HIGH — blocks PR-1 merge.

### N10 — `dataflow/trust/__init__.py` has circular self-import at load time

Verified: `trust/__init__.py:24` has `from dataflow.trust import (...)` inside itself as part of `__all__` reflection. This is not harmful today but if PR-3 decides to "wire trust/ into core/audit_integration.py" instead of deleting, the circular load order must be resolved. Severity: LOW — flag before PR-3 decides.

## Plan amendments required

1. **PR-3 deletion manifest must list EVERY dependent file per target**. Before any delete, run `git grep -l` per target and document. Use `workspaces/dataflow-perfection/02-plans/02-deletion-safety-log.md` (already referenced but not created) as the source of truth.

2. **PR-1 security fixes need a stopgap `quote_identifier()`**, because PR-4 (which provides the canonical helper) runs after PR-1. Options: (a) PR-1 inlines a minimal `_safe_identifier(name)` helper and PR-4 replaces it, or (b) PR-1 is re-sequenced after PR-4. Option (a) is cleaner because PR-4 depends on PR-3 which depends on PR-1. **Recommend option (a).**

3. **Version conflict with issue-354**: master plan must decide:
   - **Option A**: Cancel issue-354, roll its scope into PR-6. Single 2.0.0 release, clean history. Impact-verse waits longer for the Redis fabric fix.
   - **Option B**: Ship issue-354 as 1.9.0 first, then the perfection sprint starts from 1.9.0 baseline → 2.0.0. Impact-verse gets the fabric fix sooner; PR-6 rebases onto 1.9.0.
   - **Recommend Option B** because the critical data leak in fabric is already scoped in issue-354 and the impact-verse deployment owner is waiting. PR-6 must then start AFTER issue-354 merges, adding ~1 cycle of sequential dependency.

4. **Patch-release strategy**: the user's comment about "impact-verse rolling forward faster" in the prompt implies they want critical fixes on 1.8.x patches. The plan does not address this. **Recommend**: ship the 9 CRITICAL security fixes (PR-1) as `1.8.1` immediately, `1.9.0` = issue-354, `2.0.0` = remaining 13 PRs. Three releases, each with a clear scope, each rollable to impact-verse independently.

5. **Exit criteria counts must use "actual → 0", not "remove N → 0"**: 89 mocks, 294 prints, 969 f-string logs. The plan's PR-11 and PR-0 use the wrong numbers for the initial grep counts.

6. **Migration history claim must be corrected** in the exec summary. 16/44 failures, not 44/44.

7. **`suppress_warnings` removal in PR-0** must track all 6 imports in `__init__.py:82-89`, not just the single invocation at line 92.

8. **Add explicit `core/error_enhancer.py` vs `platform/errors.py::ErrorEnhancer` resolution** to PR-3 (Pattern E additional entry).

9. **Add `FabricTenantRequiredError` ownership note** to PR-5 or PR-6 (whichever ships first) to prevent double-definition.

10. **Verify `pyproject.toml` vs `__init__.py:95` version string** (1.7.1 in **init**.py observed). PR-0 must start from the actual version.

## Scope integrity check

### Overlap with `workspaces/issue-354/`

Files modified by both plans:

| File                                | issue-354 change                                           | dataflow-perfection change                                 | Conflict                               |
| ----------------------------------- | ---------------------------------------------------------- | ---------------------------------------------------------- | -------------------------------------- |
| `fabric/pipeline.py`                | Delete 3 dicts, `_queue`, async cache methods              | PR-6 inherits issue-354 + wires endpoints                  | Transitive OK if issue-354 lands first |
| `fabric/runtime.py`                 | `_get_or_create_redis_client`, tenant_extractor plumbing   | PR-6: pass Nexus, wire scheduler, wire webhooks            | **Conflict** — both modify `start()`   |
| `fabric/serving.py`                 | Accept `tenant_extractor`, replace `get_cached` signatures | PR-6: register routes with Nexus                           | **Conflict** — same constructor diff   |
| `fabric/health.py`                  | Use `get_metadata(key)` fast path                          | PR-6: register health route                                | Compatible                             |
| `fabric/products.py`                | Tenant enforcement on cache ops                            | PR-6: tenant plumbing                                      | Compatible (superset)                  |
| `fabric/metrics.py`                 | Register new counters + gauge                              | PR-10: add metric definitions                              | **Conflict** — double-add risk         |
| `fabric/change_detector.py:274-296` | Delete paired block                                        | PR-6 inherits                                              | OK if sequenced                        |
| `core/engine.py`                    | `self._redis_url = redis_url` assignment                   | PR-2 TransactionManager real impl modifies same `__init__` | Merge discipline needed                |
| `dataflow/__init__.py`              | Version bump to 1.9.0                                      | PR-0 version bump to 2.0.0-dev.1                           | **Hard conflict** — version string     |
| `pyproject.toml`                    | Version bump to 1.9.0                                      | PR-0 version bump to 2.0.0-dev.1                           | **Hard conflict**                      |
| `CHANGELOG.md`                      | 1.9.0 entry                                                | 2.0.0 entry                                                | **Conflict — two entries, ordering**   |
| `README.md` lines 404,420,426       | Correct Redis claims                                       | PR-12 docstring audit                                      | Superset OK if PR-12 runs after        |
| `.claude/rules/dataflow-pool.md`    | Extend Rule 3                                              | PR-13 rule extensions                                      | Compatible (PR-13 extends further)     |
| `.claude/rules/testing.md`          | Extend with Redis integration test rule                    | PR-13 no-mocking enforcement                               | Compatible                             |

**Verdict**: Not integrated cleanly. The perfection plan says "PR-6 integrates issue-354 plan" but treats it as theoretical, not as a live branch that could land in parallel. **If issue-354 ships first**, every one of these files comes into PR-6 with the issue-354 diff already present, which means the master plan's file-level change descriptions are wrong for ~12 files. Need explicit rebase strategy or scope merge.

### Duplicate work between perfection PRs

| PR-A | PR-B  | Overlap                                                                                                                                             |
| ---- | ----- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| PR-1 | PR-8  | Both modify `core/nodes.py:2192-2258` (security whitelist vs query safety). Same file.                                                              |
| PR-2 | PR-7  | Both modify `core/model_registry.py` (transaction wrapping vs async conversion).                                                                    |
| PR-3 | PR-4  | PR-3 deletes `sqlite_enterprise.py`; PR-4 has bypass-pool fixes for `sqlite_enterprise.py` "if the latter survives PR-3" — non-deterministic scope. |
| PR-3 | PR-8  | PR-3 deletes `dataflow/classification/`; PR-8 deliverable 7 says "wire OR delete" classification. Contradiction.                                    |
| PR-5 | PR-6  | Both modify `fabric/cache` and tenant plumbing. PR-5 "blocks PR-6" is correct but scope overlap must be documented.                                 |
| PR-0 | PR-10 | PR-0 deletes `suppress_warnings.py` and 301 prints; PR-10 also talks about print removal. Double work.                                              |

**Fix**: write a **single shared file-ownership matrix** mapping every source file to the ONE PR that touches it. Any file touched by 2+ PRs either (a) merges into one PR or (b) defines strict sequencing with a rebase protocol.

### Rollback feasibility per PR

| PR    | Revertable standalone?                                                                                                                                                                                                               |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| PR-0  | Yes (infrastructure only).                                                                                                                                                                                                           |
| PR-1  | **Risky** — security fixes depend on PR-1 staying in. Reverting PR-1 after PR-3/PR-4 merge would re-introduce SQL injection on a codebase that already dropped the dead paths. Recommend: PR-1 is "keep or re-land", never "revert". |
| PR-2  | Yes if PR-7 is not yet merged.                                                                                                                                                                                                       |
| PR-3  | **Not revertable after PR-4** — PR-4 consolidates onto deleted dialect systems.                                                                                                                                                      |
| PR-4  | Yes but expensive (dialect consolidation touches every adapter).                                                                                                                                                                     |
| PR-5  | Yes (cache layer isolated).                                                                                                                                                                                                          |
| PR-6  | Yes but blocks fabric endpoints going live.                                                                                                                                                                                          |
| PR-7  | Yes.                                                                                                                                                                                                                                 |
| PR-8  | Yes.                                                                                                                                                                                                                                 |
| PR-10 | Yes (observability additive).                                                                                                                                                                                                        |
| PR-11 | Yes (test-only).                                                                                                                                                                                                                     |

**Key risk**: the plan's "revert any PR without affecting others" promise is false for PR-1 → PR-3 → PR-4 chain. Amendment: add explicit "no-revert window" documentation for this chain.

## Nice-to-have additions to the plan

1. **Add a PR for `__init__.py` public API audit**. Every `__all__` entry must map to a real implementation. Candidate: fold into PR-12.
2. **Add a regression test for the executive summary itself** — a pytest that reads this red-team findings doc and asserts every file:line claim. Prevents future audits from drifting.
3. **Add cross-repo blast radius check for `impact-verse`, `aegis`, `aether`** — grep their codebases for `db.transactions`, `db.connection`, `db.tenants`, `DynamicUpdateNode`, `@classify`, `SemanticMemoryNode` to size the breaking-change impact BEFORE PR-12's CHANGELOG.
4. **Add observability for the fix itself** — PR-0 should stand up a dashboard that tracks "findings remaining" per subsystem across the sprint. Otherwise the red team of the fix cannot tell whether all ~325 findings actually closed.
5. **Freeze `validate_queries=False` as a rule violation** in PR-13 — any new call site with this flag fails pre-commit.

## Final recommendation

**Verdict: PASS WITH AMENDMENTS. Blocked for `/todos` until the following are corrected**:

1. Exec summary: fix the "44 all failed" migration history claim (it's 16/44).
2. Exec summary: correct grep counts (294 prints, 89 mocks, 969 f-string logs — the 969 is already correct).
3. Master plan: resolve version conflict with `workspaces/issue-354/` — recommend patch 1.8.1 + 1.9.0 + 2.0.0 strategy.
4. Master plan: PR-1 stopgap `_safe_identifier` helper (break the PR-1 → PR-4 cycle).
5. Master plan: complete dependency graph for every PR-3 deletion target, with dependent files named.
6. Master plan: single file-ownership matrix showing every file → one PR, with rebase protocol for shared files.
7. Master plan: add `FabricTenantRequiredError` and `ErrorEnhancer` dual-impl entries.
8. Master plan: track all 6 `suppress_warnings` imports in PR-0, not just the 1 call.
9. Master plan: verify and fix current version string (`__init__.py:95` shows 1.7.1, not 1.8.0).
10. Master plan: PR-11 exit criteria reworded to "from actual grep → 0" not "remove 118 → 0".

**The architectural verdict stands.** DataFlow is foundationally broken, every CRITICAL security finding reproduces at source, the façade managers are real, the observability collapse is real, the orphan subsystems are real. The plan gets the shape right and the work allocation mostly right. The amendments above address sequencing gaps, quantitative overstatements, and the cross-plan conflict with issue-354. After amendment, the 14-PR plan with autonomous parallel execution and ~21 cycles is sound.

**Do not skip issue-354 integration**. The highest-impact user (impact-verse) is waiting on the fabric Redis fix — the perfection plan must not block that while it rebuilds DataFlow end-to-end. Ship the Express cache tenant fix and the SQL injection fixes as 1.8.1 immediately; ship issue-354 as 1.9.0 within a cycle; complete 2.0.0 against a 1.9.0 baseline. Three releases respect the user's urgency and the red team's constraints.
