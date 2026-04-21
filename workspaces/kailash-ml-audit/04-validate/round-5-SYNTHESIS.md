# Round 5 /redteam Synthesis

**Date:** 2026-04-21
**Scope:** 15 ml-_-draft.md + 6 supporting-_-draft.md specs + 2 Phase-E meta drafts (ml-readme-quickstart-body, ml-index-amendments) post-Phase-E.

## Aggregate verdict: ALMOST CONVERGED (5/8 personas CONVERGED/PASS)

| Audit                  | Round-4                    | Round-5                                     | Status                        |
| ---------------------- | -------------------------- | ------------------------------------------- | ----------------------------- |
| Cross-spec consistency | 0 CRIT + 0 HIGH + 1 MED    | 0 CRIT + **2 HIGH** + 1 MED                 | ↓ regression via N1 + HIGH-E1 |
| Closure verification   | 31/31 GREEN, 3 YELLOW      | 15/16 GREEN, **1 RED** (N1), 2 accepted     | PARTIAL                       |
| Newbie UX              | 6/6 GREEN, 1 MED           | **6/6 GREEN, 0 HIGH, 0 MED, 1 LOW**         | ✅ CONVERGED                  |
| Feasibility            | 5 HIGH, 17/21 READY        | 9 HIGH (4 resurfaced), 14/23 READY          | PARTIAL                       |
| Industry parity        | 24/25 GREEN                | **24/25 GREEN, 0 regression**               | ✅ PASS                       |
| TBD re-triage          | 0/0/0 + 12 drifts          | **0/0/0 + 0 new TBDs**                      | ✅ CONVERGED                  |
| Senior practitioner    | CERTIFIED + 1 HIGH (A10-3) | **CERTIFIED + 0 HIGH + 1 new MED**          | ✅ CERTIFIED                  |
| Spec-compliance        | 14/14 PASS + 2 MED         | **18/20 PASS + 2 HIGH regressions + 3 MED** | PARTIAL                       |

**Progress Round-4 → Round-5:**

- Industry parity: **24/25 GREEN maintained** ✅
- Senior practitioner: **CERTIFIED** holds ✅ (A10-3 closed by Phase-E)
- Newbie UX: **converged** (M-1 env var closed by Phase-E MUST 1b)
- TBD: **0 new** from Phase-E
- But N1 DDL regression persists across 5 personas (cross-spec, closure, feasibility, TBD, spec-compliance)

## Consolidated open items (6 HIGHs unique + 5 MEDs)

### Theme-A: DDL prefix unification (5 personas agree)

**N1 / HIGH-R5-2 / B1 regression** — `ml-tracking` uses `kml_*` for 8 tables + ml-diagnostics + kaizen-ml + align-ml still on `kml_*`; 5 siblings use `_kml_*` for 16+ tables. Phase-E E2 swept 5 specs toward `_kml_*` but missed ml-tracking + 3 others. Cross-spec FK referential-integrity drift — NOT cosmetic. Violates `approved-decisions.md` + `rules/dataflow-identifier-safety.md` Rule 2.

### Theme-B: Env helper plumbing incomplete

**HIGH-E1** — `_env.resolve_store_url()` declared in ml-engines-v2 §2.1 MUST 1b but not plumbed to 4 sibling specs (ml-tracking §2.5, ml-registry, ml-feature-store, ml-automl). Violates `rules/security.md` Multi-Site Kwarg Plumbing that the MUST itself cites.

### Theme-C: RegisterResult field-shape drift (NEW spec-compliance HIGH)

**HIGH-R5-1** — `ml-registry §7.1` declares `RegisterResult.artifact_uri: str` (singular) but `ml-engines-v2 §16.3` Tier-2 test + `ml-readme-quickstart-body §2` consume `artifact_uris: dict[str, str]` (plural dict). Regression guard would raise `AttributeError`.

### Theme-D: kaizen-ml integration gap (NEW senior-practitioner MED)

**A11-NEW-1** — `ml-engines-v2-addendum §E11.3 MUST 1` mandates Kaizen agents obtain ML method signatures via `km.engine_info()`, but `supporting-specs-draft/kaizen-ml-integration-draft.md` has ZERO hits for EngineInfo / km.engine_info / km.list_engines. Cross-spec drift per `specs-authority.md §5b`.

### Theme-E: km.lineage signature divergence (NEW newbie-UX LOW)

**L-1** — `km.lineage` requires `tenant_id: str` kwarg (no default) while every sibling km.\* verb defaults `tenant_id: str | None = None` with ambient resolution via `get_current_tenant_id()`. Day-0 newbie hits `TypeError` on `await km.lineage(run_id)`.

### Theme-F: Minor editorials (absorbed into Phase-F)

- MED-R5-1: `RegisterResult.onnx_status` in §5.6.2 but not in §7.1 canonical
- MED-R5-2: ml-serving L239 `# (Decision 8)` inline still unqualified (Phase-D partial)
- MED-R5-3: `lineage` in **all** but missing from §15.9 eager-import example
- MED-N2: `EngineInfo.clearance_level` axis `Literal["D","T","R","DTR"]` vs §E9.2 vocab L/M/H
- YELLOW-G: §E13.1 `engine.lineage(...)` pseudocode vs canonical `km.lineage(...)`
- YELLOW-H: `km.engine_info` / `km.list_engines` **all** placement not specified

## Phase-F plan (focused, ~75 min, 6 sub-shards in parallel)

**F1: DDL prefix unification in ml-tracking + 3 drifted specs (~30 min)**

- Rewrite ml-tracking DDL `kml_*` → `_kml_*` (8 CREATE TABLE + ~40 in-prose references + §TBD T-02 PIN update)
- Sweep ml-diagnostics L515 `SELECT COUNT(DISTINCT step) FROM kml_metric` → `_kml_metric`
- kaizen-ml-integration L273 `kml_runs` → `_kml_run` (singular + underscore)
- align-ml-integration L277+L350 `kml_metrics` → `_kml_metric`

**F2: `_env.resolve_store_url` plumbing note (~10 min)**

- Add one-sentence cross-ref to ml-tracking §2.5, ml-registry §2.x, ml-feature-store §2.x, ml-automl §2.x citing ml-engines-v2 §2.1 MUST 1b

**F3: RegisterResult field-shape fix (~5 min)**

- ml-registry §7.1: `artifact_uri: str` → `artifact_uris: dict[str, str]` + add `onnx_status: Optional[Literal["clean","custom_ops","legacy_pickle_only"]] = None`

**F4: kaizen-ml integration §2.4 Agent Tool Discovery (~15 min)**

- Add §2.4 "Agent Tool Discovery via km.engine_info()" binding E11.3 MUST 1
- Document the discovery contract + tenant-scoped lookup + version-sync invariant

**F5: km.lineage default + editorials (~10 min)**

- `km.lineage(..., tenant_id: str | None = None)` with ambient resolution note
- YELLOW-G: §E13.1 pseudocode `engine.lineage(...)` → `km.lineage(...)`
- YELLOW-H: specify km.engine_info / km.list_engines in **all** Group 1 or new Group 6 ("Discovery")

**F6: Final cleanups (~5 min)**

- MED-R5-2 ml-serving L239 qualify `(Decision 8)` citation
- MED-R5-3 `lineage` in §15.9 eager-import example + §18 checklist line 2453
- MED-N2 EngineInfo.clearance_level type — clarify or split

## Round-6 entry criteria

After Phase-F merges:

- Re-run all 8 Round-5 personas
- Target: 0 CRIT + 0 HIGH + ≤2 MED across all 8 audits
- If clean → **FIRST CLEAN ROUND** (since Round 5 already has 5/8 pass, Round 6 should pass remaining 3)
- Round 7 confirms convergence (2 consecutive clean rounds)

## What's CERTIFIED today (unchanged from Round 4)

- 14/14 user-approved decisions pinned
- All 12 Phase-B CRITs closed
- Industry parity 24/25 GREEN
- Senior-practitioner CERTIFIED
- 7-package wave release documented
- kailash-rs#502 parity issue updated
- All 4 CRITs (DB URL, tracker constructor, MLError hierarchy, get_current_run) remain GREEN
