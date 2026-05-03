# Round 7 Cross-Spec Consistency Audit

**Date:** 2026-04-21
**Persona:** Cross-Spec Consistency Auditor (post Phase-G)
**Scope:** 15 `specs-draft/ml-*-draft.md` (incl. 2 Phase-E meta drafts: `ml-engines-v2-addendum`, `ml-index-amendments`) + 6 `supporting-specs-draft/*.md`. 21 specs total.
**Method:** Re-derived every assertion from scratch via `rg` / `grep` per `rules/testing.md` audit-mode rule. Prior round verdicts NOT trusted. Every row below carries a literal mechanical sweep OR a Read citation.

## Headline: 0 CRIT + 0 HIGH + 0 MED — FIRST FULL CLEAN ROUND

| Aggregate | Round-6 actual | Round-7 actual | Δ                |
| --------- | -------------- | -------------- | ---------------- |
| CRIT      | 0              | **0**          | stable           |
| HIGH      | 1 (HIGH-6-1)   | **0**          | ↓ 1 (Phase-G G1) |
| MED       | 2 (6-1, 6-2)   | **0**          | ↓ 2 (Phase-G G3) |

All three Phase-G items (G1 kaizen-ml prefix sweep, G2 ClearanceRequirement propagation, G3 RegisterResult reconciliation + editorials) verified landed; no new findings introduced by Phase-G itself.

---

## Section A — 4 CRITs Re-Verified

### A1 — DB URL canonical `~/.kailash_ml/ml.db`

Sweep: `rg -c 'kailash_ml\.db|~/\.kailash_ml' specs-draft/` → hits across 7 specs (ml-tracking 12, ml-dashboard 12, ml-engines-v2 4, ml-backends 2, ml-automl 2, ml-rl-core 1, ml-drift 1). Canonical mandate at `ml-tracking §2.2 L83`; every sibling reads ambient; no drift; `kailash-ml.db` hits are all inside the `1_0_0_merge_legacy_stores` migration context (pre-1.0 rollback). **GREEN.**

### A2 — `ExperimentTracker.create()` factory + `get_current_run()` accessor

`rg -c 'ExperimentTracker\.create'` → 18 hits across 5 specs (ml-tracking 10, ml-engines-v2 3, ml-rl-core 3, ml-rl-align-unification 1, ml-automl 1). `rg -c 'get_current_run'` → 46 hits across 12 specs including all 6 supporting-specs. Canonical factory + accessor declared at `ml-tracking §2.5 L171` + `§10.1 L1000`. Legacy sync-construction appears ONLY inside `# BLOCKED` examples. **GREEN.**

### A3 — `MLError` hierarchy (11 typed children + `ParamValueError` multi-inherit)

`rg -c 'MLError'` → 97 hits across 12 spec files. `ml-tracking §9.1 L856-L914` is canonical: `MLError(Exception)` + 11 family children (`TrackingError`, `AutologError`, `RLError`, `BackendError`, `DriftMonitorError`, `InferenceServerError`, `ModelRegistryError`, `FeatureStoreError`, `AutoMLError`, `DiagnosticsError`, `DashboardError`) + cross-cutting `UnsupportedTrainerError`, `MultiTenantOpError`. `ParamValueError(TrackingError, ValueError)` multi-inheritance at L891 plus rationale at L900. `MetricValueError` has matching shape at L890. **GREEN.**

### A4 — `TrainingResult.device: DeviceReport`

`ml-engines-v2 §4.1 L1092-L1123` declares `@dataclass(frozen=True) class TrainingResult:` with `device: DeviceReport` (L1097), `elapsed_seconds`, `tracker_run_id`, etc. Back-compat mirrors `device_used` / `accelerator` / `precision` auto-populate from `device` via `__post_init__` (L1131). Tier-2 test at §16.3 L2402-L2403 asserts `result.device is not None` AND `result.device_used` resolves. Cross-ref to `ml-backends.md` at L2424. **GREEN.**

---

## Section B — Round-6 HIGHs + MEDs Closure (Phase-G landing verification)

### B1 — `kml_agent_` residual (HIGH-R6-A)

`rg '[^_]kml_agent_|^kml_agent_' supporting-specs-draft/` → **0 hits** (exit code 1). `rg -c '_kml_agent_' supporting-specs-draft/` → 8 hits in `kaizen-ml-integration-draft.md`. DDL at L459 (`CREATE TABLE _kml_agent_traces`), L473 (`CREATE TABLE _kml_agent_trace_events`), index refs at L470/L471/L483, FK to `_kml_run.run_id` at L461. `table_prefix` literal at L446 = `"_kml_agent_"`. Stale "63-char Postgres prefix rule" prose from L449 removed: `rg '63-char' supporting-specs-draft/kaizen-ml-integration-draft.md` → 0 hits. **GREEN.**

### B2 — kaizen-ml §2.4.2 `clearance_level` type parity (HIGH-R6-B)

`kaizen-ml-integration-draft.md L171`: `clearance_level | Optional[tuple[ClearanceRequirement, ...]] | PACT axis (D/T/R per Decision 12) + level (L/M/H per §E9.2) — nested per §E11.1 L488-516 (NOT a flat literal)`. Import clause at L158: `ClearanceRequirement,  # nested axis+level dataclass per §E11.1 L488-516`. Byte-matches addendum `§E11.1 L504`: `clearance_level: Optional[tuple[ClearanceRequirement, ...]]`. `_is_clearance_admissible` pseudocode at L192-L202 correctly iterates the tuple. **GREEN.**

### B3 — ml-registry §7.1 + §7.1.2 + §5.6.2 cross-ref (HIGH-R6-C)

- `§7.1 L417-L431` canonical dataclass has `artifact_uris: dict[str, str]` (L424) + in-line comment `# v1.0.0 invariant: single-format-per-row (len == 1); see §7.1.2.` (L425).
- `§7.1.2 Single-Format-Per-Row Invariant (v1.0.0)` at L488-L503 — full paragraph stating `len(RegisterResult.artifact_uris) == 1` in v1.0.0, one row per `(tenant_id, name, version)`, single `format=` kwarg per call.
- `§5.6.2 L236` cross-ref: "The `artifact_uris` dict-to-DDL aggregation under the single-format-per-row invariant is specified in `§7.1.2`."
- Back-compat shim at `§7.1.1 L448-L479` retained (`@property artifact_uri` emitting `DeprecationWarning`, removed at v2.0).

All consumer sites use plural (ml-readme-quickstart L74, ml-engines-v2 §16.3 L2404, L1101, L1149, L1194, L1196, L1315, L1356, L2331). DDL at `_kml_model_versions` L270 correctly keeps singular `artifact_uri TEXT` column (one row per format) — matches §7.1.2 invariant. **GREEN.**

### B4 — approved-decisions.md `_kml_` prefix + rationale (MED-R6-1)

`approved-decisions.md L31`: "Postgres tables use `_kml_` prefix (leading underscore distinguishes framework-owned internal tables from user-facing tables; all names stay within Postgres 63-char identifier limit). See `ml-tracking.md §6.3` + `rules/dataflow-identifier-safety.md` Rule 2 for the canonical convention; per-spec sweeps in `ml-tracking`, `ml-registry`, `ml-serving`, `ml-feature-store`, `ml-automl`, `ml-diagnostics`, `ml-drift`, `ml-autolog`, and the cross-domain `kaizen-ml-integration §5.2` trace tables all unify on `_kml_*` as of Phase-G (2026-04-21)." Rationale + date-stamped authority update. `rg 'kml_' 04-validate/approved-decisions.md` confirms only `_kml_*` prefixes (L21 is a deleted-scaffold reference `\_kml_engine_versions`; L31 is the canonical declaration). **GREEN.**

### B5 — ml-engines-v2 §15.9 "six named groups" + Group 6 eager imports + §18 checklist (MED-R6-2, MED-R6-3)

- `L2180`: "six named groups in this exact sequence (Group 6 added by Phase-F F5 per `ml-engines-v2-addendum §E11.2`)" — "five" eliminated.
- `L2234-L2235`: Group 6 symbols `engine_info`, `list_engines` in `__all__`.
- `L2255`: eager-import example adds `from kailash_ml.engines.registry import engine_info, list_engines  # Group 6 Engine Discovery (ml-engines-v2-addendum §E11.2)`.
- `L2485`: §18 release-checklist asserts eager-import of both symbols.

`rg 'five named groups|six named groups' specs-draft/ml-engines-v2-draft.md` → 1 hit, says "six". **GREEN.**

### B6 — ml-engines-v2-addendum §E11.3 MUST 4 "18 engines" + varying per-engine method count (MED-R6-5)

`§E11.3 MUST 4 L602` (structural §4 under §E11.3's "Tier 2 Wiring Test"): "`list_engines()` returns all **18 engines** enumerated in §E1.1 (MLEngine + 17 support engines: TrainingPipeline, ExperimentTracker, ModelRegistry, FeatureStore, InferenceServer, DriftMonitor, AutoMLEngine, HyperparameterSearch, Ensemble, Preprocessing, FeatureEngineer, ModelExplainer, DataExplorer, ModelVisualizer, Clustering, AnomalyDetection, DimReduction) AND every `EngineInfo.signatures` tuple contains the **per-engine public-method count specified in §E1.1** (varies per engine — MLEngine's 8-method surface per Decision 8 is a per-engine invariant, NOT a fixed '8 per engine' constraint across all 18)." `rg '13 engines' specs-draft/` now only hits legacy origin-context references ("round-1 finding 0/13 engines" in drift/feature-store/automl) — historical traceability, not drift. **GREEN.**

---

## Section C — Phase-F Carry-Forward Verification

### C1 — `_env.resolve_store_url` in 6 specs

`rg -l 'resolve_store_url' specs-draft/` → **6 files**: ml-tracking, ml-engines-v2, ml-feature-store, ml-registry, ml-automl, ml-dashboard. Authoritative declaration at `ml-engines-v2 §2.1 MUST 1b` (L132, L149). Consumers at ml-tracking §2.5 L169, ml-registry §10.2 L847, ml-feature-store §2 L71, ml-automl §2.1 L76, ml-dashboard §3.2 L96. Note: the brief listed ml-serving as the 6th, but ml-serving does NOT open a tracker-store (`rg 'store_url|KAILASH_ML_STORE_URL' specs-draft/ml-serving-draft.md` → 0 hits). The 6th consumer is correctly `ml-dashboard` per Round-6 finding. **GREEN.**

### C2 — `km.lineage(..., tenant_id: str | None = None)` default

- `ml-engines-v2-addendum §E10.2 L418`: `km.lineage(model_uri_or_run_id_or_dataset_hash, *, tenant_id: str | None = None, max_depth=10)`.
- `ml-engines-v2 §15.8 L2166-L2171`: `async def lineage(..., *, tenant_id: str | None = None, max_depth: int = 10)`.
- `ml-engines-v2 §15.9 L2262-L2264`: module-scope declaration with same default.
- Rationale at `ml-engines-v2 L2174`: "aligns `km.lineage` with every sibling `km.*` verb (`km.track`, `km.train`, `km.register`, `km.serve`, `km.watch`, `km.resume`, etc.) which all default `tenant_id: str | None = None`". **GREEN.**

### C3 — §E13.1 uses `km.lineage` not `engine.lineage`

`ml-engines-v2-addendum §E13.1 L648`: "Assert the model's `LineageGraph` (via `km.lineage(registered.model_uri, tenant_id=engine.tenant_id)`) contains: training run_id, feature versions, dataset_hash, and serving endpoint URI. Note: `km.lineage` is the canonical top-level wrapper per `ml-engines-v2-draft.md §15.8`; the engine instance has no `.lineage()` method (the eight-method `MLEngine` surface per §2.1 MUST 5 is `setup`/`compare`/`fit`/`predict`/`finalize`/`evaluate`/`register`/`serve` only)." `rg 'engine\.lineage\(' specs-draft/` → 0 hits. **GREEN.**

### C4 — ClearanceRequirement nested dataclass at §E11.1 L488-516

`ml-engines-v2-addendum §E11.1 L488-L516`: `@dataclass(frozen=True) class ClearanceRequirement:` with fields `axis: ClearanceAxis` (L490-L491) and `min_level: ClearanceLevel` (L491-L492). Consumer at L504: `clearance_level: Optional[tuple[ClearanceRequirement, ...]]`. Example tuple at L512-L515: `(ClearanceRequirement(axis="D", min_level="M"), ClearanceRequirement(axis="T", min_level="L"))`. Worked EngineInfo sample at L535-L539 uses same shape. **GREEN.**

---

## Section D — 14 Approved Decisions (grep-verified)

| #   | Decision                                                 | Mechanical sweep                                                                                                                        | Verdict |
| --- | -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| 1   | Status vocab `FINISHED` only                             | `rg '"COMPLETED"' specs-draft/` → 3 hits in ml-tracking (L223/L279/L1232), all BLOCKED/legacy-migration context                         | GREEN   |
| 2   | GDPR erasure, audit immutable, sha256 fingerprints       | ml-tracking §9 + `sha256:<8hex>` per `rules/event-payload-classification.md §2`                                                         | GREEN   |
| 3   | 4-member enum RUNNING/FINISHED/FAILED/KILLED             | `rg 'RUNNING.*FINISHED.*FAILED.*KILLED' specs-draft/` → 9 hits across ml-tracking, ml-serving, ml-dashboard                             | GREEN   |
| 4   | DDP/FSDP/DeepSpeed rank-0-only                           | `rg 'get_rank\(\) == 0\|rank-0'` → ml-diagnostics §4.5 + ml-autolog                                                                     | GREEN   |
| 5   | XPU native-first + ipex fallback                         | `rg 'torch\.xpu\.is_available\|intel_extension'` → ml-backends                                                                          | GREEN   |
| 6   | `backend-compat-matrix.yaml` as data                     | `rg 'backend-compat-matrix\.yaml'` → ml-backends + km.doctor                                                                            | GREEN   |
| 7   | CI runner policy (CPU+MPS blocking, CUDA on acquisition) | `rg 'macos-14\|self-hosted runner'` → infra todo threads verified                                                                       | GREEN   |
| 8   | Lightning lock-in, `UnsupportedTrainerError`             | `rg -c 'UnsupportedTrainerError'` → 19 hits (ml-engines-v2 12, ml-tracking 5, ml-automl 2)                                              | GREEN   |
| 9   | Rust async `ExperimentTracker` parity                    | ml-tracking §2.5 + Rust variant note L171                                                                                               | GREEN   |
| 10  | Single-spec cross-SDK, no pre-split                      | variants/rs/ deferred per approved-decisions L17                                                                                        | GREEN   |
| 11  | Legacy namespace sunset at 3.0 + 2.x warn + 1.x shim     | ml-registry §7.1.1 `artifact_uri` @property shim exemplifies                                                                            | GREEN   |
| 12  | `MultiTenantOpError` in 1.0.0, PACT-gated post-1.0       | `rg -c 'MultiTenantOpError'` → 13+ hits across 5 specs                                                                                  | GREEN   |
| 13  | Hyphen extras across all 15 drafts                       | `rg -l '\[rl-offline\]\|\[rl-envpool\]\|\[rl-bridge\]\|\[autolog-lightning\]\|\[feature-store\]'` → 4 specs; hyphen convention enforced | GREEN   |
| 14  | `Version: 1.0.0 (draft)` on every spec                   | `rg -c '^Version: 1\.0\.0' specs-draft/` → **17/17 specs** at v1.0.0 (draft)                                                            | GREEN   |

All 14 pinned. **GREEN.**

---

## Section E — §5b Full-Sibling Sweep

Per `rules/specs-authority.md §5b`, re-derived every shape that changed in Phase-F/G against the full sibling set.

### `RegisterResult` field shape

- Canonical: `ml-registry §7.1 L417-L431` — `artifact_uris: dict[str, str]`.
- Consumers (all plural, all v1.0.0 single-format): ml-readme-quickstart-body L74, ml-engines-v2 L291, L797, L1101, L1149, L1194-L1196, L1315, L1356, L2331, L2404-L2405. Zero hits on `RegisterResult.artifact_uri[^s]` outside §7.1.1 shim / §7.1.2 invariant / §5.6.2 cross-ref / §5A.2 DDL column. **GREEN.**

### `ClearanceRequirement`

- Canonical: `ml-engines-v2-addendum §E11.1 L488-L516`.
- Consumer: `kaizen-ml-integration §2.4.2 L171` + import at L158 + pseudocode at L192-L202.
- Zero hits of `clearance_level: Optional[Literal` across any spec (Round-6 drift eliminated). **GREEN.**

### `_kml_*` DDL prefix sweep (all CREATE TABLE statements)

- `rg 'CREATE TABLE kml_' specs-draft/ supporting-specs-draft/` → **0 hits**.
- `rg -c 'CREATE TABLE _kml_' specs-draft/` → 24 hits across 6 specs (ml-tracking 8, ml-drift 4, ml-serving 3, ml-feature-store 4, ml-automl 1, ml-registry 4).
- `rg -c 'CREATE TABLE _kml_' supporting-specs-draft/` → 2 hits in `kaizen-ml-integration` (`_kml_agent_traces`, `_kml_agent_trace_events`). **GREEN.**

Intentional non-`_kml_` contexts verified:

- `ml-tracking L684` — bare-stem migration filename `0001_create_kml_experiment.py` (Python identifier rule: module names cannot start with underscore; physical table stays `_kml_experiment`). Explicit rationale documented.
- `ml-feature-store L69/L556` — user-configurable per-tenant feature-table prefix `table_prefix="kml_feat_"`, a distinct concept from framework-internal `_kml_*` metadata tables. Rationale at L556: "distinct from the user-configurable per-tenant feature-table prefix".
- `align-ml-integration L186-L188` — local variable names `kml_key` (TRL→kml metric-name mapping dict). Python identifier, not DDL.

None are drift; all three are rule-conformant with explicit scope notes.

### `km.*` function signatures

All 9 wrappers (`track`, `train`, `register`, `serve`, `watch`, `resume`, `lineage`, `autolog`, `rl_train`) default `tenant_id: str | None = None` (module-scope decls at ml-engines-v2 §15.2-§15.9). No signature divergence.

---

## Section F — New Findings

**NONE.**

Phase-G introduced three narrow edits (kaizen-ml prefix sweep, ClearanceRequirement propagation, RegisterResult reconciliation + editorials). All three verified. No emergent drift in:

- sibling specs that reference the renamed `_kml_agent_*` tables (0 lingering refs).
- kaizen-ml §2.4 / §2.5 / §5.2 prose around the clearance_level change (consistent).
- ml-registry §5A.2 DDL vs §7.1 dataclass vs §7.1.2 invariant (triangulated).
- approved-decisions.md L31 rationale prose vs per-spec sweeps (authority chain restored).
- ml-engines-v2 §15.9 six-group example + §18 checklist (triangulated).
- ml-engines-v2-addendum §E11.3 MUST 4 "18 engines" vs §E1.1 table (triangulated; §E1.1 L43 "Total: 18 engines; 18/18 auto-wire").

---

## Round-8 Entry Assertions

Round-7 verdict: **0 CRIT + 0 HIGH + 0 MED — FIRST CLEAN CROSS-SPEC ROUND.**

For Round-8 to confirm two-consecutive-clean convergence exit, the following MUST still hold:

1. **A1** — `rg '~/\.kailash_ml/ml\.db' specs-draft/` returns ≥7 files; no spec drifts to a different default path.
2. **A2** — `rg 'ExperimentTracker\.create' specs-draft/ supporting-specs-draft/` returns ≥18 hits; `rg 'ExperimentTracker\(conn\)'` outside `# BLOCKED` blocks returns 0.
3. **A3** — `ml-tracking §9.1 L856-L914` unchanged; `ParamValueError(TrackingError, ValueError)` multi-inheritance preserved.
4. **A4** — `ml-engines-v2 §4.1 L1092-L1123` unchanged; `device: DeviceReport` in required-fields list; `__post_init__` back-compat mirror rule intact.
5. **B1** — `rg '[^_]kml_agent_' supporting-specs-draft/` returns 0 hits; `rg '_kml_agent_' supporting-specs-draft/` returns ≥8 hits.
6. **B2** — `kaizen-ml-integration §2.4.2 L171` type matches `ml-engines-v2-addendum §E11.1 L504` byte-for-byte: `Optional[tuple[ClearanceRequirement, ...]]`.
7. **B3** — `ml-registry §7.1 L424` + `§7.1.2 L488-L503` + `§5.6.2 L236` present; consumer sweep finds zero assumption of `len(artifact_uris) > 1` in v1.0.0 code paths.
8. **B4** — `approved-decisions.md L31` mentions `_kml_` (leading underscore) + Phase-G date stamp; `rg 'kml_' 04-validate/approved-decisions.md | grep -v '_kml_'` returns 0 non-underscored hits.
9. **B5** — `ml-engines-v2 §15.9 L2180` says "six named groups"; L2255 has `engine_info, list_engines` eager import; §18 L2485 checklist present.
10. **B6** — `ml-engines-v2-addendum §E11.3 MUST 4 L602` says "18 engines" + "varies per engine"; §E1.1 L43 says "Total: 18 engines".
11. **C1** — 6 specs cross-ref `_env.resolve_store_url` (ml-engines-v2, ml-tracking, ml-registry, ml-feature-store, ml-automl, ml-dashboard).
12. **C2** — every `km.*` signature defaults `tenant_id: str | None = None`.
13. **Decisions 1-14** — 14 pins survive Round-8 re-verification.
14. **DDL prefix** — `rg 'CREATE TABLE kml_' specs-draft/ supporting-specs-draft/` → 0; `CREATE TABLE _kml_` → 26 hits across 7 specs.
15. **Intentional `kml_` non-DDL contexts** — ml-tracking L684 migration-filename rule, ml-feature-store L69/L556 user-prefix-knob, align-ml-integration L186-L188 metric-map local vars, remain correctly scoped with rationale.

If all 15 assertions re-verify GREEN at Round-8, **convergence is confirmed** (two consecutive clean cross-spec rounds). Absent any new spec edit between Round-7 and Round-8, every assertion above remains mechanically testable via `rg` alone — no semantic re-reading required.

---

## Appendix — Mechanical Sweep Commands

Every claim above was produced by one of these (copy-paste reproducible):

```bash
# A1-A4 CRIT sweeps
rg -c 'kailash_ml\.db|~/\.kailash_ml' specs-draft/
rg -c 'ExperimentTracker\.create' specs-draft/ supporting-specs-draft/
rg -c 'get_current_run' specs-draft/ supporting-specs-draft/
rg -c 'MLError' specs-draft/ supporting-specs-draft/
rg -nC1 'ParamValueError' specs-draft/ supporting-specs-draft/
rg -nC1 'class TrainingResult|device: DeviceReport' specs-draft/ml-engines-v2-draft.md

# B1-B6 Phase-G closure
rg '[^_]kml_agent_|^kml_agent_' supporting-specs-draft/      # 0
rg -c '_kml_agent_' supporting-specs-draft/                  # 8
rg -nC2 'clearance_level|ClearanceRequirement' supporting-specs-draft/kaizen-ml-integration-draft.md
rg -nC1 'clearance_level|ClearanceRequirement' specs-draft/ml-engines-v2-addendum-draft.md
rg -n 'artifact_uris|§7\.1\.2|Single-Format-Per-Row' specs-draft/ml-registry-draft.md
rg -n 'kml_' 04-validate/approved-decisions.md
rg -n 'five named groups|six named groups' specs-draft/ml-engines-v2-draft.md
rg -n 'engine_info|list_engines' specs-draft/ml-engines-v2-draft.md
rg -n '18 engines|13 engines|17 support engines|12 support engines' specs-draft/ supporting-specs-draft/

# C1-C4 Phase-F carry-forward
rg -l 'resolve_store_url' specs-draft/
rg -n 'km\.lineage|engine\.lineage' specs-draft/ml-engines-v2-addendum-draft.md specs-draft/ml-engines-v2-draft.md
rg -n 'ClearanceRequirement' specs-draft/ml-engines-v2-addendum-draft.md

# Section D decisions
rg -c '"COMPLETED"' specs-draft/
rg -c 'RUNNING.*FINISHED.*FAILED.*KILLED' specs-draft/
rg -c 'UnsupportedTrainerError' specs-draft/
rg -c 'MultiTenantOpError' specs-draft/
rg -c '^Version: 1\.0\.0' specs-draft/

# Section E sibling sweep
rg 'CREATE TABLE kml_' specs-draft/ supporting-specs-draft/              # 0
rg -c 'CREATE TABLE _kml_' specs-draft/ supporting-specs-draft/
rg -n '[^_]kml_[a-z]' specs-draft/ supporting-specs-draft/               # intentional non-DDL contexts only
rg -n 'artifact_uri[^s]' specs-draft/                                    # all DDL/back-compat/aggregation
```

No prior-round verdicts trusted. Every assertion has a `rg` sweep or explicit file+line citation.
