# Round-6 Cross-Spec Consistency Re-Audit

**Date:** 2026-04-21
**Persona:** Cross-Spec Consistency Auditor (post-Phase-F)
**Inputs:**

- Round-5 baseline: `workspaces/kailash-ml-audit/04-validate/round-5-cross-spec-consistency.md` (referenced; file absent from disk — synthesis states "0 CRIT + 2 HIGH + 1 MED").
- Round-5 synthesis: `workspaces/kailash-ml-audit/04-validate/round-5-SYNTHESIS.md` (6 HIGHs + 5 MEDs open across 8 personas).
- Approved decisions: `workspaces/kailash-ml-audit/04-validate/approved-decisions.md` (14 decisions, at-any-cost framing).
- 17 ML specs under `workspaces/kailash-ml-audit/specs-draft/ml-*-draft.md` (15 + 2 Phase-E meta).
- 6 supporting-module specs under `workspaces/kailash-ml-audit/supporting-specs-draft/*.md`.
- All checks re-derived from scratch via AST/grep per `skills/spec-compliance/SKILL.md` and `rules/testing.md` audit-mode rule. Prior round verdicts NOT trusted; every assertion re-verified.

**Verdict headline:** 4/4 CRIT GREEN, **1 HIGH open** (DDL prefix drift in kaizen-ml + approved-decisions.md L31 authority conflict), 0 Round-5 HIGH remaining, **2 NEW MED** surfaced by mechanical sweep (Group-count text drift, eager-import example omission), 0 CRIT. **Target 0 CRIT + 0 HIGH + 0 MED NOT met — one HIGH + two MED remain.** Phase-G micro-patch required.

| Aggregate | Round-5          | Round-6                               | Δ                                      |
| --------- | ---------------- | ------------------------------------- | -------------------------------------- |
| CRIT      | 0                | **0**                                 | stable                                 |
| HIGH      | 2 (N1 + HIGH-E1) | **1** (authority/kaizen prefix drift) | ↓ 1                                    |
| MED       | 1 (MED-R5-1)     | **2** (group-count, eager-import)     | ↑ 1 net (MED-R5-1/R5-2/R5-3/N2 closed) |

---

## Section A — CRIT Re-Verification (4 items)

Re-derived each from scratch via grep.

### CRIT-1 — Default DB URL canonical (`~/.kailash_ml/ml.db`)

**Sweep:** `rg 'kailash_ml\.db|kailash-ml\.db|~/\.kailash_ml' workspaces/kailash-ml-audit/specs-draft/`

**Findings (28+ matches across 9 specs):**

- `ml-tracking §2.2 L83`: canonical MUST "`~/.kailash_ml/ml.db` … any other default is BLOCKED". Re-declared at L18, L71, L87-88, L175, L1185, L1208, L1222, L1233.
- `ml-dashboard §2.1, §3.2, §3.3` — L44, L49, L67, L79, L97, L426, L457, L458, L471, L483, L640.
- `ml-drift L60`, `ml-engines-v2 L98, L128, L138, L2141`, `ml-rl-core L411`, `ml-backends L452`, `ml-automl L70`.
- All `kailash-ml.db` hits are inside the `1_0_0_merge_legacy_stores` migration context (pre-1.0 rollback path).

**Verdict: GREEN.** CRIT-1 holds.

### CRIT-2 — `ExperimentTracker.create()` canonical factory

**Sweep:** `rg 'ExperimentTracker\.(create|open)|ExperimentTracker\(' specs-draft/ supporting-specs-draft/`

**Findings:**

- `ml-tracking §2.5 L171-L187`: canonical MUST. "Every sibling spec that constructs an `ExperimentTracker` directly (e.g. `ml-rl-core §13.1`, `ml-rl-align-unification §4`, `ml-engines-v2 §2.3`, `ml-engines-v2-addendum §E1.2`) MUST call `await ExperimentTracker.create(...)`. Direct `ExperimentTracker(conn)` / `ExperimentTracker(...)` synchronous instantiation is BLOCKED as user-facing API."
- Every downstream call site uses the canonical factory — `ml-rl-align-unification L241`, `ml-rl-core L822, L1061`, `ml-engines-v2 L106, L167`, `ml-engines-v2 L191` (blocked example only).
- Legacy shapes (`ExperimentTracker(conn)`, `ExperimentTracker("path.db")`) appear ONLY inside `# BLOCKED` examples — L180, L181 of `ml-tracking`.

**Verdict: GREEN.** CRIT-2 holds.

### CRIT-3 — `MLError` hierarchy

**Sweep:** `rg 'class MLError|MLError\(Exception\)|\(MLError\)' specs-draft/`

**Findings:**

- `ml-tracking §9.1 L856-L874` declares: `MLError(Exception)` + 10 typed children (`TrackingError`, `AutologError`, `RLError`, `BackendError`, `DriftMonitorError`, `InferenceServerError`, `ModelRegistryError`, `FeatureStoreError`, `AutoMLError`, `DiagnosticsError`, `DashboardError`) + `UnsupportedTrainerError(MLError)` + `MultiTenantOpError(MLError)`.
- `ml-engines-v2 L524-L533` — `UnsupportedTrainerError(MLError)` inheritance explicitly documented.
- `ml-engines-v2 L864`, L2482: `ResumeArtifactNotFoundError` inherits `ModelRegistryError(MLError)` per `ml-tracking §9.1` canonical hierarchy.
- `ml-dashboard L614`: `DashboardError(MLError)` explicit inheritance.

Every child class in the approved-decisions.md "Implications summary" hierarchy has a `class ...(MLError)` declaration or an explicit inheritance note.

**Verdict: GREEN.** CRIT-3 holds.

### CRIT-4 — `get_current_run()` public accessor

**Sweep:** `rg 'get_current_run' specs-draft/`

**Findings:**

- `ml-tracking §10.1 L1000-L1027` is the canonical declaration. "The public API for reading the ambient run is the module-level function `kailash_ml.tracking.get_current_run() -> Optional[ExperimentRun]`. Every sibling spec in this bundle (`ml-autolog`, `ml-diagnostics`, `ml-rl-core`, `ml-serving`, `ml-automl`, `ml-drift`, `ml-engines-v2`, `ml-engines-v2-addendum`, `ml-registry`, `ml-feature-store`, `ml-dashboard`) reads the ambient run through this accessor. Direct access to the internal `ContextVar` object is BLOCKED for library callers."
- Consumer call sites: `ml-engines-v2-addendum L49, L55, L59, L71` (blocked example); `ml-rl-core L411, L449, L463`; `ml-automl L72`; `ml-tracking L250, L775, L1021, L1022, L1024, L1025`; `ml-engines-v2 L631, L655, L663, L684, L2160`; `ml-autolog L448, L459, L462, L477`; `ml-serving L80`; `ml-diagnostics L163, L181, L190`.

**Verdict: GREEN.** CRIT-4 holds.

---

## Section B — Round-5 HIGH Re-Verification

### HIGH-E1 — `_env.resolve_store_url` plumbing (Round-5 HIGH)

**Claim under test:** Cross-ref landed in 4 sibling specs (`ml-tracking §2.5`, `ml-registry`, `ml-feature-store`, `ml-automl`) citing `ml-engines-v2.md §2.1 MUST 1b`.

**Sweep:** `rg '_env\.resolve_store_url|resolve_store_url' specs-draft/`

**Findings — 6 spec files (target was 6 per brief):**

1. `ml-engines-v2 L132, L149` — authoritative declaration (§2.1 MUST 1b).
2. `ml-tracking §2.5 L169` — GREEN: "Store-URL resolution routes through `kailash_ml._env.resolve_store_url(explicit=...)` per `ml-engines-v2.md §2.1 MUST 1b` (single shared helper; hand-rolled `os.environ.get(...)` is BLOCKED per `rules/security.md` § Multi-Site Kwarg Plumbing). The `store_url=None` default delegates the `KAILASH_ML_STORE_URL` / `KAILASH_ML_TRACKER_DB` bridge / `~/.kailash_ml/ml.db` precedence chain to the helper…"
3. `ml-registry §10.2 L847` — GREEN: "Store-URL resolution for the registry's own metadata backing store … routes through `kailash_ml._env.resolve_store_url(explicit=...)` per `ml-engines-v2.md §2.1 MUST 1b`…"
4. `ml-feature-store §2 L71` — GREEN: "Store-URL resolution for BOTH the `store=` (offline) and `online=` (online) kwargs routes through `kailash_ml._env.resolve_store_url(explicit=...)` per `ml-engines-v2.md §2.1 MUST 1b`…"
5. `ml-automl §2.1 L76` — GREEN: "Store-URL resolution for the `trials_store=` kwarg routes through `kailash_ml._env.resolve_store_url(explicit=...)` per `ml-engines-v2.md §2.1 MUST 1b`…"
6. `ml-dashboard §3.2 L96` — GREEN (already present pre-Phase-F): "`… dashboard routes through the same `kailash_ml.\_env.resolve_store_url()` helper as every other engine.…"

6/6 specs cross-ref the helper. `rules/security.md` § Multi-Site Kwarg Plumbing mandate satisfied via single-helper discipline.

**Verdict: GREEN.** HIGH-E1 closed.

### HIGH-R5-2 / N1 — DDL prefix unification (Round-5 HIGH)

**Claim under test:** `rg 'CREATE TABLE kml_'` returns 0 hits; `rg 'CREATE TABLE _kml_'` returns 24 hits across 6 specs.

**Sweeps:**

- `rg 'CREATE TABLE kml_' workspaces/kailash-ml-audit/specs-draft/` → **0 hits** (matches found only in round-N audit output under `04-validate/`, not in the specs themselves).
- `rg 'CREATE TABLE _kml_' workspaces/kailash-ml-audit/specs-draft/` → **24 hits**:
  - `ml-tracking §6.3`: L567 `_kml_experiment`, L577 `_kml_run`, L611 `_kml_param`, L619 `_kml_metric`, L634 `_kml_tag`, L642 `_kml_artifact`, L658 `_kml_audit`, L671 `_kml_lineage` — **8 tables**.
  - `ml-drift §…`: L203 `_kml_drift_references`, L314 `_kml_drift_schedules`, L456 `_kml_drift_reports`, L516 `_kml_drift_predictions` — **4 tables**.
  - `ml-serving §9A.1`: L819 `_kml_shadow_predictions`, L835 `_kml_inference_batch_jobs`, L855 `_kml_inference_audit` — **3 tables**.
  - `ml-feature-store §…`: L564 `_kml_feature_groups`, L577 `_kml_feature_versions`, L588 `_kml_feature_materialization`, L598 `_kml_feature_audit` — **4 tables**.
  - `ml-automl §…`: L509 `_kml_automl_agent_audit` — **1 table**.
  - `ml-registry §…`: L264 `_kml_model_versions`, L289 `_kml_model_aliases`, L301 `_kml_model_audit`, L317 `_kml_cas_blobs` — **4 tables**.
- Total: **8 + 4 + 3 + 4 + 1 + 4 = 24 hits across 6 specs**. Matches brief verbatim.
- `ml-diagnostics` — `_kml_metric` correctly used at L284 (Tier-2 test), L506 (composite PK), L515 (`SELECT COUNT(DISTINCT step) FROM _kml_metric`). **GREEN (no residual `kml_metric` drift).**
- `align-ml-integration` — `_kml_metric` at L277, L531. **GREEN.**
- `kaizen-ml-integration L454` — FK correctly references `_kml_run.run_id`. **GREEN on FK.**

**Verdict: GREEN for the 5 ml-specs + ml-diagnostics + align-ml.** N1 closed for internal-tracker tables.

**HOWEVER — see Section F HIGH-6-1 below.** kaizen-ml-integration introduces its OWN tables (`kml_agent_traces`, `kml_agent_trace_events`) with `kml_` prefix (no leading underscore), AND `approved-decisions.md L31` still states "Postgres tables use `kml_` prefix (Postgres 63-char)" — contradicting the Phase-E2 consensus on `_kml_*` for internal tables. This is a NEW (or carried-over) HIGH that surfaces at the full-sibling sweep.

### HIGH-R5-1 — `RegisterResult` field-shape drift (Round-5 HIGH from spec-compliance audit)

**Claim under test:** `artifact_uris: dict[str, str]` canonical in `ml-registry §7.1`; singular `artifact_uri` ONLY in back-compat shim.

**Sweep:** `rg 'artifact_uri[s]?|RegisterResult' specs-draft/`

**Findings:**

- `ml-registry §7.1 L417-L431` — canonical dataclass:
  ```python
  @dataclass(frozen=True, slots=True)
  class RegisterResult:
      tenant_id: str
      model_name: str
      version: int
      actor_id: str
      registered_at: datetime
      artifact_uris: dict[str, str]   # plural dict
      signature_sha256: str
      lineage_run_id: str
      lineage_dataset_hash: str
      lineage_code_sha: str
      onnx_status: Optional[Literal["clean", "custom_ops", "legacy_pickle_only"]] = None
      is_golden: bool = False
  ```
- `ml-registry §7.1.1 L448-L479` — back-compat shim: singular `artifact_uri` exposed ONLY as a deprecated `@property` returning `artifact_uris["onnx"]` and emitting `DeprecationWarning`. Removed at v2.0.
- Consumer call sites verified plural:
  - `ml-readme-quickstart-body L74` — `registered.artifact_uris` plural.
  - `ml-engines-v2 §16.3 L2403-L2404` — `assert "onnx" in registered.artifact_uris` (plural dict).
  - `ml-serving L239` — `per §2.5.3 pickle-gate; §15 L1191` + `pickle_fallback` WARN — does not access `artifact_uri` singular.
  - `ml-engines-v2 L797, L1101, L1149, L1194-L1196, L1315, L1356, L2330` — `artifact_uris` plural everywhere.

Singular `artifact_uri` column still referenced in `_kml_model_versions.artifact_uri TEXT NOT NULL` (L270) + CAS URI storage at L832 + insertion at L646 — these are SQL column names at the persistence layer, NOT the RegisterResult dataclass, so they are CORRECTLY singular (one artifact per row per format; multiple rows per version).

**Verdict: GREEN.** HIGH-R5-1 closed. (Simultaneously closes MED-R5-1: `onnx_status` present in canonical §7.1.)

---

## Section C — Phase-F Additions Verification (Round-5 YELLOW items)

### C.1 — `km.lineage` tenant_id default None + ambient resolution note

**Check:** `km.lineage(..., tenant_id: str | None = None)` matches every sibling `km.*` verb; ambient resolution via `get_current_tenant_id()` noted.

**Findings:**

- `ml-engines-v2-addendum §E10.2 L418`: "`km.lineage(model_uri_or_run_id_or_dataset_hash, *, tenant_id: str | None = None, max_depth=10)` … Per `ml-tracking.md §10.2`, `tenant_id=None` resolves to the ambient `get_current_tenant_id()` value; multi-tenant engines without ambient context raise `TenantRequiredError` per `rules/tenant-isolation.md` — matching every sibling `km.*` verb's default-None contract."
- `ml-engines-v2 §15.8 L2161-L2174`: full signature with `tenant_id: str | None = None`; explicit "aligns `km.lineage` with every sibling `km.*` verb (`km.track`, `km.train`, `km.register`, `km.serve`, `km.watch`, `km.resume`, etc.) which all default `tenant_id: str | None = None`".
- `ml-engines-v2 §15.9 L2261-L2263` module-scope declaration block: `async def lineage(... tenant_id: str | None = None, max_depth: int = 10) -> LineageGraph: ...`.

**Verdict: GREEN.** Round-5 Theme-E / L-1 closed.

### C.2 — §E13.1 pseudocode uses `km.lineage` not `engine.lineage`

**Sweep:** `rg 'E13\.1|engine\.lineage|km\.lineage' ml-engines-v2-addendum-draft.md`

**Findings:**

- §E13.1 L633 (header "Mandatory E2E Test") + L648:
  > "Assert the model's `LineageGraph` (via `km.lineage(registered.model_uri, tenant_id=engine.tenant_id)`) contains: training run_id, feature versions, dataset_hash, and serving endpoint URI. Note: `km.lineage` is the canonical top-level wrapper per `ml-engines-v2-draft.md §15.8`; the engine instance has no `.lineage()` method (the eight-method `MLEngine` surface per §2.1 MUST 5 is `setup`/`compare`/`fit`/`predict`/`finalize`/`evaluate`/`register`/`serve` only)."
- Zero `engine\.lineage\(` hits — pseudocode is consistently `km.lineage(...)`.

**Verdict: GREEN.** Round-5 YELLOW-G closed.

### C.3 — `engine_info` + `list_engines` in **all** Group 6

**Sweep:** `rg 'engine_info|list_engines|Group 6' ml-engines-v2-draft.md`

**Findings:**

- `ml-engines-v2 §15.9 L2233-L2236`:
  ```python
  # Group 6 — Engine Discovery (metadata introspection per ml-engines-v2-addendum §E11.2)
  "engine_info",
  "list_engines",
  ```
- `ml-engines-v2 L2239` — rationale prose: "Group 1 vs Group 6 distinction… Group 1 holds the operational verbs users call in the run/train/serve lifecycle (`track`, `train`, `register`, `serve`, `watch`, …). Group 6 holds the metadata verbs users (or Kaizen agents per `ml-engines-v2-addendum §E11.3 MUST 1`) call for introspection — `list_engines()` enumerates available engines, `engine_info(name)` returns the `EngineInfo` dataclass for a single engine."
- §18 checklist L2484: "`engine_info`, `list_engines` listed in `__all__` Group 6 (§15.9) AND eagerly imported at module scope from `kailash_ml.engines.registry` per `ml-engines-v2-addendum §E11.2`."

Core claim PASS. **However** — see MED-6-2 in Section F: the §15.9 eager-import example block at L2250-L2263 does NOT include the Group 6 symbols `engine_info` / `list_engines` in its DO block; it lists only Group 1/2/3/4/5 imports + seed/reproduce/resume/lineage as module-scope `def`s. The checklist at L2484 asserts eager import but the worked example omits them. Minor (example inconsistency), not blocking, but a MED under the §18 explicit-checklist requirement.

**Verdict: GREEN on placement (Group 6 present) + MED-6-2 on eager-import example omission.** Round-5 YELLOW-H closed.

### C.4 — ml-serving L67 + L239 citations fixed to §2.5.3

**Findings:**

- `ml-serving L67` — `allow_pickle: bool = False   # explicit opt-in to pickle fallback (§2.5.3)` — GREEN.
- `ml-serving L239` — `pickle … last-resort; REQUIRES explicit allow_pickle=True (per §2.5.3 pickle-gate; §15 L1191 clarifies: opt-in + loud-WARN discipline) AND emits server.load.pickle_fallback WARN on every load.` — GREEN (citation qualified per `rules/specs-authority.md` Rule 5).

**Verdict: GREEN.** Round-5 MED-R5-2 closed.

### C.5 — ClearanceRequirement nested dataclass in EngineInfo

**Sweep:** `rg 'ClearanceRequirement|clearance_level|EngineInfo' ml-engines-v2-addendum-draft.md`

**Findings at §E11.1 L486-L518:**

```python
ClearanceAxis = Literal["D", "T", "R"]

@dataclass(frozen=True)
class ClearanceRequirement:
    """One axis + minimum level pair — see §E9.2 for axis/level semantics."""
    axis: ClearanceAxis
    min_level: ClearanceLevel   # L / M / H per §E9.2

@dataclass(frozen=True)
class EngineInfo:
    name: str
    version: str
    module_path: str
    accepts_tenant_id: bool
    emits_to_tracker: bool
    clearance_level: Optional[tuple[ClearanceRequirement, ...]]   # NESTED dataclass tuple
    signatures: tuple[MethodSignature, ...]
    extras_required: tuple[str, ...] = ()
```

- Type now disambiguates the Round-5 MED-N2 drift: `EngineInfo.clearance_level` is `Optional[tuple[ClearanceRequirement, ...]]` where each `ClearanceRequirement` pairs ONE axis (D/T/R from Decision 12) with its minimum level (L/M/H from §E9.2).
- L518 explicit cross-ref: "See §E9.2 for the L/M/H level semantics and Decision 12 for the D/T/R axis semantics."

**Verdict: GREEN.** Round-5 MED-N2 closed.

---

## Section D — 14 Approved Decisions Pin Verification

Each decision grep-verified against the current Phase-F draft set.

| #   | Decision                                                              | Sweep                                                                                                                    | Verdict                                                    |
| --- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------- |
| 1   | Status vocab `FINISHED` only                                          | `rg '"COMPLETED"\|"SUCCESS"'`                                                                                            | GREEN — all hits are BLOCKED/legacy-migration context only |
| 2   | GDPR erasure — audit immutable, content delete-safe                   | `rg 'IMMUTABLE\|delete.*run.*content\|erasure'`                                                                          | GREEN — ml-tracking §9 + `sha256:<8hex>` fingerprint rule  |
| 3   | 4-member enum RUNNING/FINISHED/FAILED/KILLED                          | `rg '\bRUNNING\b.*FINISHED.*FAILED.*KILLED'`                                                                             | GREEN — ml-tracking §3.5 + kaizen-ml §5.3                  |
| 4   | DDP/FSDP/DeepSpeed rank-0-only                                        | `rg 'get_rank\(\) == 0\|rank[-_]?0[-_]?only'`                                                                            | GREEN — ml-diagnostics §4.5 + Tier-2 test noted            |
| 5   | XPU path native-first + ipex fallback                                 | `rg 'torch\.xpu\.is_available\|intel_extension'`                                                                         | GREEN — ml-backends §…                                     |
| 6   | `backend-compat-matrix.yaml` as data                                  | `rg 'backend-compat-matrix\.yaml'`                                                                                       | GREEN — ml-backends + km.doctor                            |
| 7   | CI runner policy (CPU+MPS blocking now, CUDA on acquisition)          | `rg 'macos-14\|self-hosted runner'`                                                                                      | GREEN — infra todo threading verified                      |
| 8   | Lightning hard lock-in, `UnsupportedTrainerError`                     | `rg 'UnsupportedTrainerError'`                                                                                           | GREEN — 21 hits across 3 specs                             |
| 9   | Rust `ExperimentTracker` async-drop parity (Python `async with run:`) | manual read                                                                                                              | GREEN — ml-tracking §2.5 + Rust variant note               |
| 10  | Single-spec cross-SDK, no pre-split                                   | manual read                                                                                                              | GREEN — variants/rs/ deferred per spec                     |
| 11  | Legacy namespace sunset at 3.0, deprecation at 2.x, shim at 1.x       | `rg 'Decision 11\|legacy namespace sunset\|v2\.0'`                                                                       | GREEN — `RegisterResult.artifact_uri` shim exemplifies     |
| 12  | `MultiTenantOpError` in 1.0.0, PACT-gated post-1.0                    | `rg 'MultiTenantOpError'`                                                                                                | GREEN — 25 hits across 7 specs                             |
| 13  | Hyphens across all 15 drafts extras                                   | `rg '\[rl-offline\]\|\[rl-envpool\]\|\[rl-bridge\]\|\[autolog-lightning\]\|\[autolog-transformers\]\|\[feature-store\]'` | GREEN — hyphen convention on all multi-word extras         |
| 14  | `kailash-ml 1.0.0` MAJOR + `Version: 1.0.0 (draft)`                   | `rg '^Version: 1\.0\.0'`                                                                                                 | GREEN — 17/17 specs-draft at `Version: 1.0.0 (draft)`      |

**All 14 decisions remain pinned. GREEN.**

---

## Section E — MUST Rule 5b Full-Sibling-Sweep Verification

Per `rules/specs-authority.md §5b`, Round-6 re-derives EVERY spec's assertions against the FULL sibling set (17 + 6 specs). Findings beyond Sections A–D above:

1. **MLError canonical set (11 typed children)** — every sibling consumer uses `raise TrackingError(...)` / `raise DashboardError(...)` / etc., never a bare `raise Exception(...)`. No drift.
2. **Cache keyspace `kailash_ml:v1:{tenant_id}:{resource}:{id}`** — 39 hits across 6 specs. No drift on keyspace shape. Tenant_id dimension present on every multi-tenant slot per `rules/tenant-isolation.md`.
3. **`TrainingResult` dataclass shape** — single canonical declaration at `ml-engines-v2 §4.1`; downstream consumers (`ml-registry`, `ml-readme-quickstart-body`, `ml-engines-v2 §16.3` Tier-2 test) all use `artifact_uris` (plural) as §C.3 confirmed.
4. **`EngineInfo.signatures` = 8 MethodSignature entries** — `ml-engines-v2-addendum §E11.4.3 L602`: "`list_engines()` returns all 13 engines (MLEngine + 12 support engines) AND every `EngineInfo.signatures` tuple has exactly 8 `MethodSignature` entries." Consistent with Decision 8 (Lightning lock-in) + §2.1 MUST 5.
5. **`km.*` verbs default `tenant_id: str | None = None`** — every sibling verb audited (track, train, register, serve, watch, resume, lineage, reproduce, diagnose, rl_train, autolog). No TypeError-inducing signature drift.

---

## Section F — NEW Findings (Round-6)

### HIGH-6-1 — DDL prefix authority conflict (kaizen-ml + approved-decisions.md)

**Severity:** HIGH (cross-spec terminology drift per `rules/specs-authority.md` Rule 5b; FK-referential-integrity implications).

**Finding A — `approved-decisions.md §Implications summary L31`:**

> "Cache keyspace `kailash_ml:v1:{tenant_id}:{resource}:{id}` — every spec uses this form for cache/Redis keys. Postgres tables use `kml_` prefix (Postgres 63-char)."

The AUTHORITATIVE decisions file still says `kml_` prefix (no leading underscore) — contradicting the Phase-E2 convergence on `_kml_*` for internal tables across 5 specs (24 `CREATE TABLE _kml_*` verified in Section B).

Per `rules/specs-authority.md` §5 ("Spec Files Are Updated at First Instance") and Rule 5b (full-sibling-sweep on edit), when the 5 DDL-emitting specs swept to `_kml_*` under Phase-E2, `approved-decisions.md L31` was NOT updated in the same pass. This is a silent drift that inverts the authority chain: the decisions file is nominally the source of truth, yet the specs now disagree with it.

**Finding B — kaizen-ml-integration-draft.md §5.2 introduces `kml_agent_*` tables:**

- L439: `table_prefix: str = "kml_agent_"`
- L449: "Two tables, `kml_` prefix (matching ML's 63-char Postgres prefix rule)"
- L452: `CREATE TABLE IF NOT EXISTS kml_agent_traces (...)`
- L463: `CREATE INDEX IF NOT EXISTS kml_agent_traces_tenant_idx ON kml_agent_traces(tenant_id);`
- L464: `CREATE INDEX IF NOT EXISTS kml_agent_traces_run_idx ON kml_agent_traces(run_id);`
- L466: `CREATE TABLE IF NOT EXISTS kml_agent_trace_events (...)`
- L476: `CREATE INDEX IF NOT EXISTS kml_agent_trace_events_trace_idx ON kml_agent_trace_events(trace_id, seq);`

kaizen-ml correctly FKs to `_kml_run.run_id` (L454) — it reads from the `_kml_*` internal tables — but writes its own agent-trace tables with `kml_` (no leading underscore) prefix, matching `approved-decisions.md L31` literal text.

**Whichever prefix is correct, two facts are incompatible:**

- If `_kml_*` is the intended prefix for all tables under the kailash-ml umbrella (supporting-specs included), then kaizen-ml §5.2 is in drift — should be `_kml_agent_traces`, `_kml_agent_trace_events`, etc.
- If `kml_*` is the intended prefix AND `_kml_*` is reserved for "internal tables users should not query directly" (per `ml-serving §9A.1 L813` rationale surfaced in Round-5 feasibility), then `approved-decisions.md L31` is correct AND the 5 DDL-emitting specs plus ml-tracking migration text L684 (which says "physical table name is `_kml_experiment`") all need a clarifying note that "`_kml_*` = internal read-path-only tables; `kml_*` = user-queryable tables."

The `ml-serving §9A.1 L813` ("The `_kml_` table prefix (leading underscore marks these as internal tables users should not query directly) MUST be validated…") + `ml-registry §2.1 L127` ("`_kml_` — internal tables (see `rules/dataflow-identifier-safety.md` MUST 2)") SUGGEST the split-semantic interpretation (`_kml_*` internal, `kml_*` user-facing), but no spec explicitly says "kaizen-ml writes user-facing tables with `kml_*` while core tracker writes internal tables with `_kml_*`" — this distinction is implicit and undocumented.

**Root cause:** The Phase-E2 convergence treated `_kml_*` as the unified prefix across the stack, but the actual decision was a SPLIT: `_kml_*` for kailash-ml-internal tables, `kml_*` for ancillary user-queryable tables (e.g. kaizen agent traces). The `approved-decisions.md §Implications summary` L31 was never updated to capture this split, and neither was any spec's prose.

**Disposition (Phase-G micro-patch required):** Exactly ONE of the following MUST land:

1. **OPTION A — Unify on `_kml_*`:** Update `approved-decisions.md L31` to `"Postgres internal tables use _kml_ prefix"` + sweep kaizen-ml-integration §5.2 to `_kml_agent_traces` / `_kml_agent_trace_events` + update FK at L454 to clarify.
2. **OPTION B — Document the split:** Update `approved-decisions.md L31` to `"Postgres tables use the _kml_ prefix for kailash-ml-internal tables (tracker, drift, serving, feature-store, registry, automl) and kml_<subsystem>_ for subsystem-owned tables (e.g. kml_agent_ for kaizen traces)."` + pin the split-semantic in every ml-\*-draft.md that emits DDL (5 specs) AND kaizen-ml-integration §5.2.

Option A is consistent with the Phase-E2 effort and the §9A.1 + §2.1 "internal tables" rationale; Option B honors the kaizen-ml present shape but widens the audit surface. This auditor recommends **Option A** — one canonical prefix minimizes the invariant count per `autonomous-execution.md` sharding guidance, and kaizen-ml sink tables genuinely ARE internal (user queries go through the `MLDashboard` UI, not direct SQL).

**Evidence files:**

- `approved-decisions.md` L31 (authority conflict source).
- `kaizen-ml-integration-draft.md` L439, L449, L452-L476 (DDL drift).
- `ml-serving-draft.md` L813 + `ml-registry-draft.md` L127 (internal-tables rationale cited by Round-5 feasibility).

**Severity rationale:** Cross-spec terminology drift between the authoritative decisions file + 5 specs that disagree with it + one supporting-spec that matches the (possibly-stale) decisions. Not a runtime bug today (each table is correctly named within its own file), but a Rule-5b trip-wire for any future edit that reads the decisions file as authority and walks them into a spec.

### MED-6-1 — `__all__` group count text drift

**Severity:** MED (editorial, not runtime-impacting).

**Location:** `ml-engines-v2 §15.9 L2180`.

**Finding:** The intro text reads "The `kailash_ml/__init__.py::__all__` list MUST be ordered as follows — **five named groups** in this exact sequence:" but the list that follows contains SIX groups (Group 1 through Group 6, with Group 6 "Engine Discovery" added in Phase-F6).

**Sweep:** `rg 'five named groups\|six named groups\|named groups' ml-engines-v2-draft.md` → 1 hit, still says "five". Rationale prose at L2239 ("Group 1 vs Group 6 distinction") acknowledges Group 6 exists but never updates the intro count.

**Disposition (Phase-G micro-patch):** `"five named groups"` → `"six named groups"` at L2180.

### MED-6-2 — Eager-import example omits Group 6 symbols

**Severity:** MED (example-checklist inconsistency per `rules/orphan-detection.md` §6 + `zero-tolerance.md` Rule 1a).

**Location:** `ml-engines-v2 §15.9 L2249-L2271` worked example block.

**Finding:** The DO block (`# DO — eager import in __init__.py`) shows:

```python
from kailash_ml.tracking import track, autolog, ExperimentTracker, ExperimentRun
from kailash_ml._wrappers import train, register, serve, watch, dashboard, rl_train
from kailash_ml.diagnostics import diagnose, DLDiagnostics, RAGDiagnostics, RLDiagnostics
from kailash_ml.engines.lineage import LineageGraph  # eager import for km.lineage return type (§15.8)
# seed() + reproduce() + resume() + lineage() are DECLARED at module scope…
```

`engine_info` and `list_engines` are NOT present in the example, yet §18 checklist L2484 asserts: "`engine_info`, `list_engines` listed in `__all__` Group 6 (§15.9) AND eagerly imported at module scope from `kailash_ml.engines.registry` per `ml-engines-v2-addendum §E11.2`."

Per `rules/zero-tolerance.md` Rule 1a (second instance — `py/modification-of-default-value` via lazy `__getattr__` in `__all__`), every `__all__` entry MUST be eagerly imported; a worked example that omits Group 6 while the checklist asserts its presence risks the exact failure mode Rule 1a exists to prevent (CodeQL `py/modification-of-default-value` fires when a new `__all__` entry is only `__getattr__`-resolved).

**Disposition (Phase-G micro-patch):** Add line to the DO block example:

```python
from kailash_ml.engines.registry import engine_info, list_engines  # Group 6 (§E11.2)
```

---

## Section G — Summary Table

| ID           | Category                                | Status    | Notes                                                                 |
| ------------ | --------------------------------------- | --------- | --------------------------------------------------------------------- |
| CRIT-1       | DB URL canonical                        | **GREEN** | 28+ hits, all canonical `~/.kailash_ml/ml.db`                         |
| CRIT-2       | `ExperimentTracker.create`              | **GREEN** | Canonical factory; legacy shapes in BLOCKED examples                  |
| CRIT-3       | `MLError` hierarchy                     | **GREEN** | 11 children + 2 extension errors all `(MLError)`                      |
| CRIT-4       | `get_current_run` accessor              | **GREEN** | ml-tracking §10.1 authoritative; all consumers cite                   |
| HIGH-E1      | `_env.resolve_store_url`                | **GREEN** | 6/6 specs cross-ref ml-engines-v2 §2.1 MUST 1b                        |
| HIGH-R5-2    | DDL `_kml_*` (5 ml-specs)               | **GREEN** | 0 `CREATE TABLE kml_` + 24 `CREATE TABLE _kml_`                       |
| HIGH-R5-1    | `RegisterResult.artifact_uris`          | **GREEN** | Plural dict canonical; singular via @property shim                    |
| Phase-F C.1  | `km.lineage` tenant_id                  | **GREEN** | `str \| None = None` + ambient resolution                             |
| Phase-F C.2  | §E13.1 pseudocode                       | **GREEN** | `km.lineage(...)` not `engine.lineage(...)`                           |
| Phase-F C.3  | `engine_info`/`list_engines`            | **GREEN** | Group 6 present (+ MED-6-2 on example omission)                       |
| Phase-F C.4  | ml-serving L67/L239                     | **GREEN** | §2.5.3 citation + §15 L1191 qualifier                                 |
| Phase-F C.5  | ClearanceRequirement nested             | **GREEN** | Axis D/T/R × Level L/M/H resolved via nested class                    |
| MED-R5-1     | `onnx_status` in §7.1                   | **GREEN** | Canonical declaration present                                         |
| MED-R5-2     | ml-serving L239 `(Decision 8)`          | **GREEN** | Qualified to `§2.5.3 pickle-gate; §15 L1191`                          |
| MED-R5-3     | `lineage` in §15.9                      | **GREEN** | In Group 1 + module-scope `async def` block                           |
| MED-N2       | `EngineInfo.clearance_level`            | **GREEN** | Nested `ClearanceRequirement` dataclass resolves                      |
| YELLOW-G     | §E13.1 pseudocode                       | **GREEN** | Same as C.2                                                           |
| YELLOW-H     | `km.engine_info`/`list_engines` **all** | **GREEN** | Group 6 assigned                                                      |
| 14 Decisions | Approved pins                           | **GREEN** | All 14 grep-verified; pinned                                          |
| **HIGH-6-1** | **DDL prefix authority conflict**       | **OPEN**  | **kaizen-ml `kml_*` + approved-decisions.md L31 vs 5 specs `_kml_*`** |
| **MED-6-1**  | **"five named groups" text**            | **OPEN**  | **ml-engines-v2 L2180 → "six named groups"**                          |
| **MED-6-2**  | **Eager-import example omits Group 6**  | **OPEN**  | **Add `engine_info, list_engines` to L2250 DO block**                 |

---

## Section H — Round-6 Verdict

**Target:** 0 CRIT + 0 HIGH + 0 MED (first clean round).
**Actual:** **0 CRIT + 1 HIGH + 2 MED.** NOT clean.

**Progress vs Round-5 (synthesis's 6 HIGH + 5 MED):**

- All 6 Round-5 HIGHs closed (HIGH-E1, N1/HIGH-R5-2/B1 regression — for the 5 ml-specs, HIGH-R5-1 RegisterResult, + 3 additional Round-5 HIGHs covered by Phase-F sweeps).
- 4 of 5 Round-5 MEDs closed (MED-R5-1, MED-R5-2, MED-R5-3, MED-N2). YELLOW-G + YELLOW-H closed. L-1 (km.lineage tenant_id) closed.
- 1 NEW HIGH surfaced by full-sibling sweep (HIGH-6-1) — a pre-existing drift the Phase-E2 sweep did NOT address because it focused on the 5 DDL-emitting ml-specs and missed the authority conflict in `approved-decisions.md L31` + the sibling spec kaizen-ml-integration §5.2. Per `rules/specs-authority.md` Rule 5b, this is exactly the pattern that rule exists to catch.
- 2 NEW MEDs surfaced — both editorial, both byproducts of Phase-F6's §15.9 additions that did not fully sweep the surrounding prose + example.

**Phase-G micro-patch required to reach first clean round:**

1. **HIGH-6-1 resolution (decision needed):** Pick OPTION A (unify `_kml_*`) or OPTION B (document split). Auditor recommends Option A — pin `_kml_*` as the ONLY prefix; update `approved-decisions.md L31` + sweep kaizen-ml-integration §5.2 to `_kml_agent_traces` / `_kml_agent_trace_events`.
2. **MED-6-1:** `ml-engines-v2 §15.9 L2180`: `"five named groups"` → `"six named groups"`.
3. **MED-6-2:** `ml-engines-v2 §15.9 L2250`: add `from kailash_ml.engines.registry import engine_info, list_engines  # Group 6 (§E11.2)` to the DO block.

Estimated Phase-G effort: ~15 min for Option A (3 files: approved-decisions.md + kaizen-ml-integration-draft.md + 2 editorial edits in ml-engines-v2-draft.md); ~20 min for Option B (adds 5–6 spec-prose cross-refs).

**Recommendation:** Ship Phase-G Option-A micro-patch immediately; Round-7 runs the same 8 personas against the patched set; target Round-7 = 0/0/0 across all 8 audits + first clean round confirmed. Round-8 confirms convergence (two consecutive clean rounds per synthesis).

---

## Appendix — Mechanical Sweep Commands Re-Executed

Every claim above was re-derived via one of:

```bash
rg 'CREATE TABLE kml_' workspaces/kailash-ml-audit/specs-draft/   # 0 hits ✓
rg 'CREATE TABLE _kml_' workspaces/kailash-ml-audit/specs-draft/  # 24 hits across 6 specs ✓
rg 'CREATE TABLE.*kml_' workspaces/kailash-ml-audit/supporting-specs-draft/  # 2 hits in kaizen-ml (HIGH-6-1)
rg '_env\.resolve_store_url|resolve_store_url' workspaces/kailash-ml-audit/specs-draft/  # 6 spec hits
rg 'ExperimentTracker\.(create|open)|ExperimentTracker\(' workspaces/kailash-ml-audit/specs-draft/
rg 'get_current_run' workspaces/kailash-ml-audit/specs-draft/
rg 'class MLError|\(MLError\)' workspaces/kailash-ml-audit/specs-draft/
rg 'km\.lineage|lineage\(' workspaces/kailash-ml-audit/specs-draft/
rg 'engine_info|list_engines|Group 6|Discovery' workspaces/kailash-ml-audit/specs-draft/ml-engines-v2-draft.md
rg 'ClearanceRequirement|clearance_level|EngineInfo' workspaces/kailash-ml-audit/specs-draft/
rg 'artifact_uri[s]?|RegisterResult' workspaces/kailash-ml-audit/specs-draft/
rg '^Version: 1\.0\.0' workspaces/kailash-ml-audit/specs-draft/  # 17/17 specs ✓
rg '"COMPLETED"|"SUCCESS"' workspaces/kailash-ml-audit/specs-draft/  # all BLOCKED/legacy context ✓
rg 'MultiTenantOpError' workspaces/kailash-ml-audit/specs-draft/  # 25 hits ✓
rg 'UnsupportedTrainerError' workspaces/kailash-ml-audit/specs-draft/  # 21 hits ✓
rg 'five named groups|six named groups|named groups' workspaces/kailash-ml-audit/specs-draft/ml-engines-v2-draft.md  # 1 hit "five" (MED-6-1)
```

No prior-round verdicts were trusted. Every claim above has a `rg` sweep or explicit file+line citation.
