# /redteam Round 2 — Integrated State

**Branch:** `integration/kailash-ml-1.5.x-followup` @ `7aa64c0a`
**Date:** 2026-04-29
**Scope:** Verify combined invariants of S1 (#699) + S2 (#700) + S3a/S3b (#701) + cleanup before /codify + release.

## A: Spec sibling re-derivation (Rule 5b)

`ls specs/ml-*.md | wc -l` → **16** (verified).

| Spec                                                                                                  | Touches changed surface                                                                                                                                                                               | Disposition                                                                                               |
| ----------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `ml-diagnostics.md`                                                                                   | EDITED on integration branch (commits `1436e8a0`, `eabd5e1e`) — §3 aliases (lines 142, 191), §5.1a `data=` wiring (lines 321, 365), names extras `[alignment]/[kaizen-judges]/[kaizen-observability]` | **MATCHED** — code+spec aligned                                                                           |
| `ml-registry.md`                                                                                      | References `_kml_model_versions` schema; spec authority for `(tenant_id, name, version)` uniqueness; §3.1 BLOCKS `"default"` and `"global"` sentinels; §3.4 mandates `tenant_id` on every alias call  | **DRIFTED — see HIGH F-1 below** (`_resolve_tenant_id` returns `"default"` not `"_single"`)               |
| `ml-tracking.md`                                                                                      | §7.2 (line 729-756) authoritative cross-spec tenant-id sentinel: `"_single"` only; explicitly BLOCKS `"default"` (line 752); `register_model` reference at line 1279                                  | **DRIFTED — same F-1**; spec is correct, code is wrong                                                    |
| `ml-engines-v2.md`                                                                                    | References `ModelRegistry.register_model(...)`, lists `tenant_id` as required at primitive boundary (line 1220)                                                                                       | NO-EDIT-NEEDED — text says signature accepts `tenant_id`; it does. Default-value drift is captured in F-1 |
| `ml-engines-v2-addendum.md`                                                                           | Lines 63-92 show `register_model` example WITH explicit `tenant_id="acme"` and explicit `TenantRequiredError` for missing                                                                             | NO-EDIT-NEEDED — example pattern correct; default-value drift is F-1                                      |
| `ml-serving.md`                                                                                       | Documents `InferenceServer` canonical 1.5.x architecture; **no mention of `MultiModelAdapter` or `from_registry_many`**                                                                               | **DRIFTED — see HIGH F-2** (S2/PR #700 added new public surface; spec was not updated)                    |
| `ml-autolog.md`                                                                                       | DLDiagnostics rank-0 references                                                                                                                                                                       | NO-EDIT-NEEDED — diagnostics changes additive, no rank-0 surface change                                   |
| `ml-drift.md`                                                                                         | Cross-references `DLDiagnostics`; line 99 references `registry.get_model(...)`                                                                                                                        | NO-EDIT-NEEDED — getter signature already required `tenant_id`                                            |
| `ml-feature-store.md`                                                                                 | tenant_id refs                                                                                                                                                                                        | NO-EDIT-NEEDED — no surface change                                                                        |
| `ml-rl-core.md`, `ml-rl-algorithms.md`, `ml-rl-align-unification.md`                                  | reference `RLDiagnostics`/`km.diagnose(kind="rl")` — alias additions don't change RL path                                                                                                             | NO-EDIT-NEEDED                                                                                            |
| `ml-backends.md`, `ml-dashboard.md`, `ml-automl.md`, `ml-integration.md`, `ml-engines-v2-addendum.md` | tenant_id refs but no surface change                                                                                                                                                                  | NO-EDIT-NEEDED                                                                                            |

**Summary:** 2 specs DRIFTED (ml-registry.md, ml-serving.md), neither was edited on integration branch.

## B: Code-vs-plan invariants

### ADR-1 (#699 — schema convergence)

| #   | Invariant                                       | Verified | Notes                                                                                                                                                                                                                            |
| --- | ----------------------------------------------- | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Migration 0005 exists (reversible up/down)      | ✅       | `0005_kml_model_versions_data_columns.py` 25,795 bytes                                                                                                                                                                           |
| 2   | ModelRegistry inline DDL deleted                | ✅       | `grep -c 'CREATE TABLE IF NOT EXISTS _kml_model_versions' packages/kailash-ml/src/kailash_ml/engines/model_registry.py` = **0**                                                                                                  |
| 3   | No `WHERE name = ?` (must be tenant+model_name) | ✅       | `grep -nE 'WHERE name = \?' packages/.../model_registry.py packages/.../lineage.py` empty                                                                                                                                        |
| 4   | Public API has `tenant_id` kwarg                | ⚠️       | AST sweep: `register_model`, `get_model`, `list_models`, `promote_model`, `get_model_versions`, `record_lineage`, `build_lineage_graph` all carry `tenant_id`. **BUT default value is `"default"`, which spec BLOCKS — see F-1** |

### ADR-2 (#700 — MultiModelAdapter)

| #   | Invariant                                              | Verified | Notes                                                                     |
| --- | ------------------------------------------------------ | -------- | ------------------------------------------------------------------------- |
| 1   | `multi_model_adapter.py` exists                        | ✅       | 13,394 bytes                                                              |
| 2   | `MultiModelAdapter in kailash_ml.__all__`              | ✅       | Python verification → `True`                                              |
| 3   | `__new__` routes 1.1.x kwargs                          | ✅       | `server.py:278-320` — closes #700 with route dispatch                     |
| 4   | `from_registry_many` is classmethod                    | ✅       | `server.py:469`                                                           |
| 5   | `MultiModelAdapter.load_model(bytes)` raises TypeError | ✅       | `multi_model_adapter.py:260` "with user-supplied bytes is removed"        |
| 6   | Production call site exists                            | ✅       | `server.py:320` (in `__new__`) imports + instantiates `MultiModelAdapter` |

### ADR-3 (#701 — diagnose data + cross-package dispatch)

| #   | Invariant                                                                           | Verified | Notes                                                                                                                                          |
| --- | ----------------------------------------------------------------------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `diagnose(kind="dl", data=loader)` consumes data                                    | ✅       | Test `test_diagnose_dl_pytorch_dataloader_end_to_end.py` passes                                                                                |
| 2   | Aliases `kind="classifier"` / `"regressor"`                                         | ✅       | Lines 511-513 in `_wrappers.py` (alias map applied at entry)                                                                                   |
| 3   | Cross-package dispatch with extras                                                  | ✅       | Lines 581 (AlignmentDiagnostics), 594 (LLMDiagnostics), 604 (AgentDiagnostics) — all `import-or-raise ImportError` with extras-name in message |
| 4   | Clustering rejected with ValueError                                                 | ✅       | `_wrappers.py:534` raises ValueError                                                                                                           |
| 5   | Unknown kwargs raise TypeError                                                      | ✅       | Test `test_diagnose_dl_unknown_kwarg_raises_typeerror` passes                                                                                  |
| 6   | `[alignment]`, `[kaizen-judges]`, `[kaizen-observability]` extras in pyproject.toml | ✅       | Lines 125-127                                                                                                                                  |

## C: Collect-only

`.venv/bin/python -m pytest --collect-only packages/kailash-ml/tests/` → **2483 collected, 4 skipped, exit 0**.

## D: Regression results

`.venv/bin/python -m pytest packages/kailash-ml/tests/regression/test_issue_69*.py packages/kailash-ml/tests/regression/test_issue_70*.py -p no:cacheprovider --tb=line -q` → **14 passed in 3.22s** (all 5 issue regression files).

Wider regression suite (`pytest packages/kailash-ml/tests/regression/`): partial run (full suite hangs on `test_rl_train_register_e2e.py` which needs real DB). 95 tests collected; observed `43 passed, 1 failed (pre-existing — see F-3), 11+ more passed before timeout on RL E2E test`.

Failing test: `test_predictions_device_invariant.py::test_every_fit_caches_last_device_report` — asserts exactly 7 concrete `fit()` methods; finds 8. **Verified pre-existing on `main`** (same failure when checked out from main). Out of scope for this workstream but per `rules/zero-tolerance.md` Rule 1 it owns whoever finds it; flag as F-3.

## E: Existing-test sweep

`.venv/bin/python -m pytest packages/kailash-ml/tests/integration/test_lineage_graph_wiring.py packages/kailash-ml/tests/regression/test_readme_lineage_quickstart.py -p no:cacheprovider --tb=line -q` → **13 passed in 1.68s**.

S1's tenant-aware port did not break the lineage tests.

## F: Pyright

Skipped — pyright not installed in `.venv` (per task instruction).

## G: Orphan / manager detection

- **MultiModelAdapter** (Manager-shape): production call site verified at `server.py:320` inside `InferenceServer.__new__` routing. Public via `__all__` (re-exported from package root). ✅
- **DriftMonitor.initialize() removal**: `grep -rn 'monitor\.initialize' packages/kailash-ml/src/` returns only the cleanup-comment lines in `_wrappers.py:335-336`. `tests/` returns empty. ✅

---

## Findings

### F-1 (HIGH) — `_resolve_tenant_id` returns spec-BLOCKED sentinel `"default"`

`packages/kailash-ml/src/kailash_ml/engines/model_registry.py:474` returns the literal `"default"` when no `tenant_id` is provided:

```python
def _resolve_tenant_id(tenant_id: str | None) -> str:
    if tenant_id is None or tenant_id == "":
        logger.debug("model_registry.tenant_default_applied",
                     extra={"resolved_tenant_id": "default"})
        return "default"
    return tenant_id
```

`specs/ml-registry.md` §3.1 (line 88) explicitly: _"The strings `"default"` and `"global"` are BLOCKED."_
`specs/ml-tracking.md` §7.2 (line 752): _`tenant_id = "default"` # BLOCKED — rules/tenant-isolation.md §2_.
`rules/tenant-isolation.md` §2: silent fallback to a default tenant is BLOCKED — must raise `TenantRequiredError`.

AST sweep confirms `register_model`, `get_model`, `list_models`, `promote_model`, `get_model_versions` all default `tenant_id="default"`. `record_lineage`, `build_lineage_graph` correctly require explicit `tenant_id`.

**Disposition options (resolve before /release):**

1. Change `_resolve_tenant_id` to return `"_single"` and update default kwarg to `tenant_id: str = "_single"` across all 5 methods (matches spec).
2. Per `rules/tenant-isolation.md` §2 + `ml-engines-v2-addendum.md:92` (which shows `await registry.register_model(training_result)` raising `TenantRequiredError`), make `tenant_id` keyword-only-required and raise `TenantRequiredError` when missing.

Option 2 is structurally stronger (no silent fallback). Option 1 is the minimum fix.

### F-2 (HIGH) — `specs/ml-serving.md` does not document MultiModelAdapter or from_registry_many

S2 (PR #700) added two public surfaces:

- `MultiModelAdapter` (re-exported via `kailash_ml.__all__`)
- `InferenceServer.from_registry_many` (classmethod)
- `InferenceServer.__new__` routing 1.1.x kwargs to `MultiModelAdapter`

`grep -nE 'MultiModelAdapter|from_registry_many|1\.1\.x' specs/ml-serving.md` → empty.

Per `rules/specs-authority.md` Rule 5 (Spec Files Are Updated At First Instance), serving spec needed an addendum at S2 merge time. Per Rule 5b, full sibling re-derivation should have surfaced this gap.

**Fix:** Add `specs/ml-serving.md` §1.5 "1.1.x Back-Compat: MultiModelAdapter + InferenceServer.**new** routing" documenting:

- The new `MultiModelAdapter` shim (one server many models, registry-only construction)
- `InferenceServer.__new__` 1.1.x routing detection
- `from_registry_many(names=..., registry=..., cache_size=...)` classmethod
- `MultiModelAdapter.load_model(bytes)` raises TypeError (no user-supplied bytes path)

### F-3 (HIGH but PRE-EXISTING) — `test_predictions_device_invariant.py` count drift

Test asserts exactly 7 concrete fit() methods; finds 8. Verified pre-existing on `main` (not introduced by this workstream).

Per `rules/zero-tolerance.md` Rule 1: "If you found it, you own it." Per Rule 1 exception: third-party-style pre-existing should be tracked with explicit owner.

**Disposition:** since this is a count-invariant the integration branch did not change, recommend a separate /fix shard to update the invariant from 7→8 (a new `fit()` method shipped between when this assertion was last reconciled and now). Could be done in same release PR or as follow-up. NOT a blocker for this workstream's /codify.

### F-4 (MEDIUM) — Workstream artifacts not present at expected paths

The orchestrator's task prompt referenced:

- `workspaces/kailash-ml-1.5.x-followup/02-plans/01-architecture-plan.md`
- `workspaces/kailash-ml-1.5.x-followup/04-validate/01-redteam-mechanical-sweep.md`
- `workspaces/kailash-ml-1.5.x-followup/journal/0001-` through `0004-`

All four are absent. Workspace contains only `todos/`. The architecture plan files exist only inside per-shard worktrees (`.claude/worktrees/s{1,2,3a,3b}-issue-*/workspaces/data-fabric-engine/`) — a different workstream artifact set. Not BLOCKING (work landed cleanly), but `/codify` cannot extract the planning artifacts unless they are first written to the workstream workspace path.

---

## Verdict

**DRIFT FINDINGS — must address F-1 + F-2 before /codify + release.**

### HIGH (Must fix before release)

- **F-1**: `_resolve_tenant_id` sentinel mismatch with spec — silent default is the exact failure mode `rules/tenant-isolation.md` §2 + `ml-tracking.md` §7.2 + `ml-registry.md` §3.1 BLOCK. Fix is mechanical: change `"default"` → `"_single"` (or raise `TenantRequiredError`).
- **F-2**: `specs/ml-serving.md` missing `MultiModelAdapter` / `from_registry_many` documentation. Fix per Rule 5/5b: add §1.5 addendum.

### HIGH (Pre-existing, recommend same release)

- **F-3**: `test_predictions_device_invariant.py` count assertion 7→8 stale — pre-existing on main. Either fix in this release or file a tracking issue.

### MEDIUM

- **F-4**: Workstream-workspace artifacts (plan + Round 1 + journals) referenced by prompt do not exist at parent paths. Non-blocking but impacts /codify extraction.

### Clean (do not block release)

- All 14 issue-specific regressions pass.
- Lineage tests + readme quickstart pass post-S1 schema port.
- `__all__` membership for `MultiModelAdapter` correct.
- DriftMonitor.initialize cleanup complete.
- Cross-package dispatch + extras correctly named.
- `pytest --collect-only` exit 0.

**Recommendation:** Do NOT proceed to /codify until F-1 + F-2 are reconciled. F-1 is a 5-line code fix; F-2 is a ~50-line spec addendum. Both fit within one shard.
