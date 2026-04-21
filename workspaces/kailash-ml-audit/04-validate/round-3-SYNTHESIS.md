# Round 3 /redteam Synthesis

**Date:** 2026-04-21
**Scope:** 15 ml-_-draft.md + 6 supporting-_-draft.md specs. Audited by 8 parallel personas.

## Aggregate verdict: NOT CONVERGED

| Audit                    | Target                      | Result                            | Met?    |
| ------------------------ | --------------------------- | --------------------------------- | ------- |
| Cross-spec consistency   | 0 CRIT + 0 HIGH             | 0 CRIT, **9 HIGH**                | —       |
| Closure verification     | ≥95% GREEN, 0 RED           | 85.7% GREEN, 10 YELLOW, **0 RED** | partial |
| Newbie UX                | 6/6 GREEN, 0 NEW HIGH       | 6/6 GREEN, **3 NEW HIGH**         | partial |
| Feasibility              | 0 HIGH, 21/21 READY         | **9 HIGH**, 0 BLOCKED, 9/15 READY | —       |
| Industry parity          | ≥22/25 GREEN                | **23/25 GREEN**                   | ✅      |
| TBD re-triage            | 0 NEEDS-DECISION, 0 BLOCKER | 0 + 0 + **12 hygiene drifts**     | partial |
| Senior practitioner      | CERTIFIED                   | CONDITIONAL (26/29 closed)        | partial |
| Spec-compliance AST/grep | every assertion PASS        | **14 HIGH + 5 MED**               | —       |

**Progress from Round-2 Phase-B:**

- **CRIT closure: 12 → 0** ✅ (all Phase-B criticals resolved)
- **HIGH closure: ~54 → ~47** (roughly flat; Phase-C closed Round-2 HIGHs but surfaced new ones in compliance sweep)
- **2026-27 architecture posture: 4 FAIL → 0 FAIL** ✅
- **Industry parity: 20/25 → 23/25** ✅ (target met)
- **Newbie scenarios: 3 GREEN → 6 GREEN** ✅ (target met)

## Consolidated open findings (~15 unique items after dedup)

### Theme-1: A10 Serving truncation gap (Phase-C Shard C-C stopped mid-A10)

1. **A10-1** — batch variable-length padding strategy undocumented
2. **A10-2** — streaming backpressure contract (`abort_on_disconnect` / `max_buffered_chunks`) undocumented
3. **A10-3** — ONNX custom-op export probe + fallback enumeration undocumented
4. **A3-3** — Prometheus histogram bucket bounds for LLM latencies not pinned
5. **A7-3** — streaming token metric split (first-token / subsequent-token / total / stream-duration) not applied

### Theme-2: Missing DDL blocks (5 specs)

6. **B6** — ml-serving: `_kml_shadow_predictions`, `_kml_inference_batch_jobs`, `_kml_inference_audit` zero `CREATE TABLE`
7. **B7** — ml-feature-store: `_kml_feature_groups`, `_kml_feature_audit`, `_kml_feature_group_history` zero `CREATE TABLE`
8. **B14** — ml-registry: `_kml_model_versions`, `_kml_model_aliases`, `_kml_model_audit`, `_kml_cas_blobs` DDL missing
9. **B15** — ml-automl: `_kml_automl_agent_audit` DDL missing

### Theme-3: Cross-spec drift

10. **Single-tenant sentinel:** `"_single"` (ml-tracking) vs `"global"` (ml-engines-v2, ml-feature-store, ml-registry, ml-serving) — sweep to pick ONE
11. **`TrainingResult` field shape:** `device_used: str` (producer) vs `device: DeviceReport` (consumer) — pick canonical shape
12. **Env var:** `KAILASH_ML_STORE_URL` (ml-engines-v2 test) vs `KAILASH_ML_TRACKER_DB` (ml-dashboard CLI) — pick ONE
13. **`km.seed` / `km.reproduce` invalid signatures** — written as `def km.seed(...)` (invalid Python); missing from `kailash_ml.__all__`
14. **`is_golden` registry schema missing** — release-gate spec mandates `is_golden=True` but ml-registry has no column/API

### Theme-4: Error hierarchy drifts

15. **`MultiTenantOpError`** (Decision 12) — zero matches across ml specs; referenced only in kailash-core-ml supporting spec
16. **`UnsupportedTrainerError`** — declared as `MLError` but inherits from generic exception in current text
17. **`ParamValueError`** — missing from §9.1 canonical list
18. **`RLTenantRequiredError`** — duplicate of canonical `TenantRequiredError`

### Theme-5: DL family + engine wiring gaps

19. **HIGH-4** — Lightning callback auto-attach at engine boundary not wired (`TrainingPipeline._train_lightning` doesn't append `as_lightning_callback()`)
20. **HIGH-5** — DDP/FSDP `strategy=` passthrough kwarg not specified engine-side
21. **HIGH-6** — `ModelCheckpoint` default + `km.resume()` top-level absent
22. **HIGH-7** — `auto_find_lr` disposition not locked
23. **HIGH-8** — `HuggingFaceTrainable` family neither specified nor formally deferred

### Theme-6: Decision-citation + hygiene drift

24. **Version drift:** 8 stale `kailash-ml 2.0 / 0.17.0 / 0.18.0` references across 6 spec files
25. **Decision 5 XPU dual-path** not codified in ml-backends
26. **Decision 6 `backend-compat-matrix.yaml`** not specified in any spec
27. **Decision 7 CI policy inverted** in ml-backends §6.3 ("GPU non-blocking") vs approved ("CPU+MPS blocking")
28. **5 residual "Open Questions" sections** in ml-backends, ml-drift, ml-serving, ml-registry, ml-autolog still read as live despite resolution
29. **3 decision-number drifts** in ml-tracking / ml-autolog / ml-dashboard citing wrong Decision N

### Theme-7: Strategic deferrals (explicit, accepted)

- ModelCard generator, cost dashboard, DatasetVersion surface, inference-time explainability, quantization/pruning/distillation primitives, BYO-judge leaderboard, identity-provider binding — all v1.1 roadmap bindings; not blocking 1.0.0.

## Phase-D shard plan (to converge toward Round 4)

One focused spec-edit session (6 shards, ~45 min total per autonomous-execution capacity bands):

- **D1: A10 Serving completion** (Theme-1) — padding, backpressure, ONNX, Prometheus buckets, token split
- **D2: DDL blocks** (Theme-2) — 4 specs × full `CREATE TABLE` schemas
- **D3: Cross-spec drift sweep** (Theme-3) — sentinel, TrainingResult, env var, km.seed/reproduce signatures, is_golden schema
- **D4: Error hierarchy completion** (Theme-4) — add MultiTenantOpError, fix UnsupportedTrainerError, add ParamValueError, delete RLTenantRequiredError duplicate
- **D5: DL family + engine wiring** (Theme-5) — Lightning auto-attach MUST, strategy passthrough, ModelCheckpoint+km.resume, auto_find_lr, HuggingFaceTrainable
- **D6: Decision citation + hygiene sweep** (Theme-6) — version drift, Decision 5/6/7 codification, "Open Questions" → "RESOLVED", decision-number fixes

## Round 4 entry criteria

After Phase-D merges:

- Re-run all 8 Round-3 personas against the fixed drafts
- Target: 0 HIGH + 0 CRIT across all 8 audits
- If Round-4 clean: Round 5 to confirm (2 consecutive clean = convergence)
- If Round-4 surfaces new HIGHs: iterate Phase-E → Round 5

## What's already certified

- All 14 user-approved decisions are pinned (some need citation cleanup)
- All 12 Round-2 CRITs closed
- All 6 Round-2 differentiators EXTENDED or STRENGTHENED
- Industry parity target (≥22/25 GREEN) exceeded
- All newbie day-0 scenarios have spec-mandated one-liners
- 2026-27 architecture future-proofing ships
- Wave-release coordination across 7 packages documented
- kailash-rs#502 parity issue updated
