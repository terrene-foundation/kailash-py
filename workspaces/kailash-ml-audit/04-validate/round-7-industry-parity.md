# Round 7 Industry-Parity Audit

**Date:** 2026-04-21
**Scope:** 25-capability matrix + differentiator posture post Phase-G
**Method:** Re-derived every cell from scratch via `Grep` / `Read` against `workspaces/kailash-ml-audit/specs-draft/` (17 ml-\*-draft.md incl. meta/readme) + `supporting-specs-draft/` (6 integration specs). Zero trust of Round-6 assertions. Phase-G edits in 5 files independently verified.

## Headline: 24/25 GREEN (Δ vs Round 6 = 0)

Round-6 score held exactly. Phase-G edits were narrow, additive, and non-structural:

- `kaizen-ml-integration §2.4` / §2.4.2 — `_kml_agent_` prefix normalization + `ClearanceRequirement` nested tuple shape pinned as the authoritative consumer shape.
- `ml-registry §7.1` L424 comment + `§7.1.2` Single-Format-Per-Row Invariant + `§5.6.2` cross-ref.
- `approved-decisions L31` — `_kml_` prefix authority language + Phase-G rollup note.
- `ml-engines-v2 §15.9` — "six named groups" wording + Group 6 eager import.
- `ml-engines-v2-addendum §E11.3 MUST 4` — "18 engines" + per-engine varying method count.

No previously-GREEN cell regressed. The single remaining non-GREEN (#7 system metrics) is unchanged from R3-R6 and remains stable-deferred to v1.1. Four Round-5 YELLOW cells (#21 agent discovery, #22 lineage default, #24 clearance typing, and #15 eager-imports in Group 6) remain closed at GREEN.

**Aggregate:** 24 GREEN + 1 PARTIAL (#7) + 0 RED + 0 MISSING.

## Matrix (25 rows)

| #   | Capability                                   | R6    | R7        | File:line                                                                                                                                                                                                                     | Note (Δ vs R6)                                                                                                                                            |
| --- | -------------------------------------------- | ----- | --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Experiment tracking (MLflow parity)          | GREEN | **GREEN** | `ml-tracking-draft.md:27` + `:57` + `:62` (`async with km.track(name) as run`) + `:152` (`ExperimentTracker.default_tenant_id`)                                                                                               | =. Canonical ExperimentTracker + `km.track()` context manager unchanged.                                                                                  |
| 2   | Model registry with signatures + provenance  | GREEN | **GREEN** | `ml-registry-draft.md:199` (signature JSONB MUST) + `:400-446` (canonical RegisterResult) + `:448` (signature_sha256) + `:488-507` (§7.1.2 single-format-per-row invariant with dict API forward-compat)                      | =. Phase-G §7.1.2 pins v1.0.0 DDL invariant WHILE preserving `artifact_uris: dict[str, str]` API shape → zero downstream drift. Differentiator untouched. |
| 3   | Model serving (online inference)             | GREEN | **GREEN** | `ml-serving-draft.md:7` + `:20` + `:53-55` (micro_batch config) + `:297` (path log)                                                                                                                                           | =. InferenceServer REST+gRPC+MCP unchanged.                                                                                                               |
| 4   | Batch/streaming inference with backpressure  | GREEN | **GREEN** | `ml-serving-draft.md:20` (online+batch+streaming) + `:54-55` + `:297` (inference_path enum)                                                                                                                                   | =. `max_buffered_chunks` backpressure pin intact.                                                                                                         |
| 5   | Shadow deployments                           | GREEN | **GREEN** | `ml-serving-draft.md:21` + `:37` (MUST NOT shadow without consumer) + `:56` (InferenceShadowSpec) + `:298` (shadow_recorded)                                                                                                  | =. Shadow-divergence → drift (§1.2) wiring intact.                                                                                                        |
| 6   | A/B testing + canary                         | GREEN | **GREEN** | `ml-serving-draft.md:21` + `:57` (InferenceCanarySpec) + `:97` (ShadowSpec alias="@challenger", percent=10)                                                                                                                   | =. Canary weights + shadow remain first-class.                                                                                                            |
| 7   | ONNX export + custom-op probe                | GREEN | **GREEN** | `ml-registry-draft.md:221-242` (§5.6 ONNX probe MUST) + `:229` (strict=True) + `:232` (ort-extensions detection) + `:234-243` (§5.6.2 onnx_status semantics) + `:436` (typed literal)                                         | =. Phase-G §5.6.2 cross-ref to §7.1.2 added without changing value semantics.                                                                             |
| 8   | Autolog (sklearn/torch/lightning/xgboost)    | GREEN | **GREEN** | `ml-autolog-draft.md:17-18` (`km.autolog` ctx manager + decorator, 7-framework dispatch)                                                                                                                                      | =. 7-framework dispatch (sklearn/Lightning/transformers/xgboost/lightgbm/statsmodels/polars).                                                             |
| 9   | Feature store (online + offline)             | GREEN | **GREEN** | `ml-feature-store-draft.md:48` (MUST both URLs) + `:54-55` (store=/online=) + `:12` (tenant isolation closed)                                                                                                                 | =. Tenant-scoped, zero-arg BLOCKED.                                                                                                                       |
| 10  | Feature lineage                              | GREEN | **GREEN** | `ml-feature-store-draft.md:31` (feature_version + entity_snapshot_hash) + engines-v2 §15 `km.lineage` surface                                                                                                                 | =. LineageGraph dataclass declared in addendum §E10.2, eagerly imported §15.9.                                                                            |
| 11  | Drift monitoring (data + concept)            | GREEN | **GREEN** | `ml-drift-draft.md:19-20` (covariate/concept table) + `:24` (drift_type Literal) + `:34-36` (performance-drift concept axis) + `:507` (label-lag aware concept check)                                                         | =. 4-type drift taxonomy intact.                                                                                                                          |
| 12  | Drift alerting                               | GREEN | **GREEN** | `ml-drift-draft.md:61` (AlertConfig) + `:88` (webhook) + `:366-398` (AlertConfig dataclass + cooldown + rate-limit send contract) + `:721` (Tier-2 test)                                                                      | =. Per-tenant bounded cooldown + hourly rate-limit.                                                                                                       |
| 13  | AutoML (agent-driven search)                 | GREEN | **GREEN** | `ml-automl-draft.md:33` (LLM-augmented first-class) + `:517` (pact_decision audit col) + `:22-24` (HPO standalone)                                                                                                            | =. Only platform with PACT-governed admission.                                                                                                            |
| 14  | Hyperparameter tuning                        | GREEN | **GREEN** | `ml-automl-draft.md:23` (HyperparameterSearch standalone) + `:78-85` (constructor)                                                                                                                                            | =.                                                                                                                                                        |
| 15  | Distributed training (DDP/FSDP/DeepSpeed)    | GREEN | **GREEN** | `ml-engines-v2-draft.md:369-373` (strategy kwarg decl) + `:647-712` (§6 MUST + usage) + `:706` (accepted strings ddp/fsdp/deepspeed) + `:712` (rank-0 gate)                                                                   | =. Lightning `Strategy` passthrough + rank-0 gating intact.                                                                                               |
| 16  | XPU/GPU/MPS backend coverage                 | GREEN | **GREEN** | `ml-backends-draft.md:22-29` (six-first-class matrix) + `:34` (bf16 compute-cap gates) + `:85-119` (§2.2.1 XPU dual-path resolver)                                                                                            | =. CUDA + MPS + ROCm + XPU + TPU + CPU.                                                                                                                   |
| 17  | RL offline (CQL/IQL/AWR/BC)                  | GREEN | **GREEN** | `ml-rl-algorithms-draft.md:30-33` (paradigm Literal incl. "offline") + `:198-242` (§5 offline RL incl. BC/CQL/IQL)                                                                                                            | =.                                                                                                                                                        |
| 18  | RL online (PPO/SAC)                          | GREEN | **GREEN** | `ml-rl-algorithms-draft.md:66-142` (PPO + §3.5 GAE pins) + `:166-170` (SAC) + d3rlpy/SB3/TRL backends                                                                                                                         | =.                                                                                                                                                        |
| 19  | Diagnostics + debugging                      | GREEN | **GREEN** | `ml-diagnostics-draft.md:14` (km.diagnose entry) + `:22-24` (routes) + `:32` (F-DIAGNOSE-NO-TOPLEVEL closed) + §5.5 (Lightning auto-attach) + §12.1 (Protocol)                                                                | =. Phase-D rank-0 auto-attach + Protocol contract intact.                                                                                                 |
| 20  | Dashboard (web UI)                           | GREEN | **GREEN** | `ml-dashboard-draft.md:8` (closes #14, #20, #15) + `:18` (MLDashboard class) + `:27` (vs MLflow/W&B/TensorBoard.dev/ClearML) + `:44-49` (canonical) + `:464` (km.dashboard notebook launcher)                                 | =. `#15 notebook-inline` remains DEFERRED (L36 → `ml-notebook.md` v1.1). Lenient reading unchanged.                                                       |
| 21  | **Agent-driven discovery** (kaizen-ml §2.4)  | GREEN | **GREEN** | `kaizen-ml-integration-draft.md:126` (§2.4 header) + `:128` (binding MUST 1) + `:136-138` (km.engine_info / km.list_engines) + `:149-160` (§2.4.2 EngineInfo re-import, NOT redefined) + `:171` (nested ClearanceRequirement) | =. Phase-G §2.4.2 strengthens: `ClearanceRequirement` nested tuple shape pinned; prefix rename `kml_agent_*` → `_kml_agent_*` is cosmetic.                |
| 22  | Reproducibility (seed + reproduce + lineage) | GREEN | **GREEN** | `ml-engines-v2-draft.md:2182-2198` (§15.9 Group 1 all 4 verbs) + `:2169-2174` (km.lineage default) + `:2254-2255` (eager imports) + `§11` seed + `§12` reproduce + `§12A` resume                                              | =. All 4 verbs default `tenant_id: str \| None = None`.                                                                                                   |
| 23  | Multi-tenant governance                      | GREEN | **GREEN** | `ml-tracking-draft.md:24` (keyspace) + `:152` + `:177` (default*tenant_id) + `ml-registry-draft.md:419` (tenant_id in RegisterResult) + approved-decisions L31 (`\_kml*` prefix authoritative)                                | =. Phase-G normalizes `_kml_` prefix across tracking/registry/serving/feature-store/automl/diagnostics/drift/autolog AND `_kml_agent_` in kaizen §5.2.    |
| 24  | PACT clearance integration                   | GREEN | **GREEN** | `ml-engines-v2-addendum-draft.md:485-516` (ClearanceAxis + ClearanceLevel + ClearanceRequirement dataclass) + `:504` (EngineInfo.clearance_level typed) + `kaizen-ml §2.4.2 L171` consumer shape                              | =. Phase-G G2 binding into kaizen §2.4.2 pins shape at consumer side without re-declaring.                                                                |
| 25  | Cross-SDK parity (Python/Rust)               | GREEN | **GREEN** | `ml-diagnostics-draft.md:879` (identical SHA-256) + `:896-897` (fingerprint Deterministic across Python + Rust) + `:909` (Tier-3 parity harness file)                                                                         | =. Fingerprint contract unchanged.                                                                                                                        |

**Scorecard:** 24 GREEN + 1 PARTIAL (#7 system metrics, stable carryover from R3–R6). Zero RED. Zero MISSING.

**#15 disposition (lenient reading, per R4/R5/R6 convention):** Row #20 captures dashboard stdout URL (GREEN); the notebook-IFrame half stays deferred to `ml-notebook.md` v1.1 (`ml-dashboard-draft.md:36`). Strict reading would hold at 23/25; lenient at 24/25.

## Regressions

**Zero regressions introduced by Phase-G.**

Verified via:

1. **`artifact_uris` plural-dict shape** — unchanged. Every downstream consumer (ml-engines-v2 `:291,1101,1149,1194-1196,1315,1356,2403`, ml-readme-quickstart-body `:74`, ml-registry `:424,440-446`) reads `artifact_uris` dict. Singular `artifact_uri` occurrences limited to: DDL column name (ml-registry `:270`, `:674`, `:860`), back-compat shim (§7.1.1), and `reference_artifact_uri` drift DDL (ml-drift `:210`). §7.1.2 explicitly notes the v1.0.0 invariant `len(artifact_uris) == 1` WITHOUT changing the dict API surface → differentiator for "forward-compat multi-format registration API" preserved; v1.1 migration is DDL-only per L500-507.

2. **`_kml_` prefix normalization** — authoritative at `approved-decisions.md:31`. Sweep across specs confirms consistent `_kml_` prefix in all DDL blocks. Kaizen §5.2 agent-trace tables now use `_kml_agent_` prefix (kaizen-ml-integration `:446`, `:459`, `:470-475`, `:483`, `:492`) — no drift.

3. **ClearanceRequirement nested tuple shape** — declared once at `ml-engines-v2-addendum-draft.md:488-516` (dataclass + axis+level), consumed at `ml-engines-v2-addendum:504` (EngineInfo.clearance_level typed as `Optional[tuple[ClearanceRequirement, ...]]`), AND at `kaizen-ml-integration-draft.md:158` + `:171` + `:193-198` + `:202`. Kaizen spec imports rather than re-declares per specs-authority Rule 5b. No drift.

4. **§15.9 six-group + Group 6 eager-import** — group ordering preserved verbatim at L2182-2236 (Lifecycle / Engine primitives / Diagnostic adapters / Backend detection / Tracker primitives / Engine Discovery). Group 6 eager imports at L2255 (`from kailash_ml.engines.registry import engine_info, list_engines`). `__all__` Group-move invariant at L2241-2243 unchanged.

5. **§E11.3 MUST 4 "18 engines" + varying method count** — at `ml-engines-v2-addendum-draft.md:602` explicitly lists all 18 engines AND clarifies "per-engine public-method count specified in §E1.1 (varies per engine — MLEngine's 8-method surface per Decision 8 is a per-engine invariant, NOT a fixed '8 per engine' constraint across all 18)". Closes the ambiguity that a narrow reading of Decision 8 could have introduced; no regression.

6. **#7 PARTIAL unchanged** — `grep -rln "SystemMetricsCollector" specs-draft/` = 0 hits. v1.1 deferral per DL-GAP-2 stable.

7. **`km.lineage(..., tenant_id: str | None = None)` Phase-F5 default** — intact at `ml-engines-v2-draft.md:2169-2174`. All `km.*` verbs (track, autolog, train, diagnose, register, serve, watch, dashboard, seed, reproduce, resume, lineage, rl_train) consistent.

## Differentiator posture Δ

| ID  | Differentiator                                   | R5           | R6           | R7               | Δ   |
| --- | ------------------------------------------------ | ------------ | ------------ | ---------------- | --- |
| D-1 | EATP governance at run level                     | EXTENDED     | EXTENDED     | **EXTENDED**     | =   |
| D-2 | Protocol-based diagnostic interop                | STRENGTHENED | STRENGTHENED | **STRENGTHENED** | =   |
| D-3 | PACT-governed AutoML                             | EXTENDED     | EXTENDED     | **EXTENDED**     | =   |
| D-4 | Engine-first RLHF + tool-use trajectories        | EXTENDED     | EXTENDED     | **EXTENDED**     | =   |
| D-5 | DataFlow × ML lineage                            | EXTENDED     | EXTENDED     | **EXTENDED**     | =   |
| D-6 | Multi-backend dashboard (SQLite → PG → DataFlow) | STRENGTHENED | STRENGTHENED | **STRENGTHENED** | =   |

**Aggregate:** 4× EXTENDED (D-1, D-3, D-4, D-5) + 2× STRENGTHENED (D-2, D-6). Unchanged from R4–R6.

**Explicit check on §7.1.2 "Single-Format-Per-Row Invariant" vs D-5 (DataFlow × ML lineage) and D-6 (Multi-backend dashboard):**

§7.1.2 does NOT weaken either differentiator. The invariant is a **DDL-side v1.0.0 constraint** (`UNIQUE (tenant_id, name, version)` blocks multi-format rows until v1.1); the **Python API shape stays `artifact_uris: dict[str, str]`** with forward-compat. L507 rationale explicitly states: "A v1.1 migration to Shape B or C is then a pure DDL addition (new UNIQUE or new JSONB column) that does NOT require re-shaping the Python return type — zero caller migration at v1.1." This is the textbook API-forward-compat / DDL-invariant-freeze pattern:

- D-5 lineage still flows `lineage_dataset_hash` + `lineage_code_sha` + `lineage_run_id` on RegisterResult (L433-435) — untouched by §7.1.2.
- D-6 dashboard reads from `_kml_model_versions` per canonical store (ml-dashboard §3.1) — the single-row-per-format DDL means the dashboard query is simpler, not more complex.

The invariant **strengthens the implementation contract** (one row = one format is trivial to reason about during CAS writes, audit-row emission, and drift-probe reads) without changing the differentiator surface.

**Bonus strengthening signals (not promoted to Δ):**

- D-3 PACT-governed AutoML — Phase-G G2's `ClearanceRequirement` nested tuple consumer binding (kaizen-ml §2.4.2 L158 + L171) means Kaizen agents now pattern-match on `(axis, min_level)` pairs through an imported dataclass rather than constructing a type by hand. Still EXTENDED (no incumbent has typed clearance axes at all); the import binding is additive depth.
- D-5 DataFlow × ML lineage — §7.1.2 single-format invariant actually simplifies the DataFlow→ML lineage query: `dataset_hash → model_version` is a 1-row lookup instead of an aggregation. Additive, not a Δ signal.

**No weakening detected.** Phase-G additions remain orthogonal to all 6 differentiators.

## Round-8 entry assertions

1. **24/25 GREEN held for 3 consecutive rounds** (R5 → R6 → R7). Convergence-entry signal firmly satisfied on industry parity.

2. **Zero regressions across Phase-G edits** (G1 kaizen-ml §2.4.2 + G2 registry §7.1.2 + G3 approved-decisions L31 + G4 engines §15.9 + G5 addendum §E11.3 MUST 4). Mechanically verified:
   - `artifact_uris` dict shape consistent everywhere; legitimate singular `artifact_uri` limited to DDL + shim.
   - `_kml_` / `_kml_agent_` prefix consistent across all DDL.
   - `ClearanceRequirement` imported (not redefined) at consumer site.
   - `__all__` six-group ordering intact; Group 6 eagerly imported.
   - "18 engines" + per-engine varying method-count clarification removes ambiguity in §E11.3 MUST 4.

3. **All 6 differentiators maintain R4–R6 posture** — 4× EXTENDED + 2× STRENGTHENED. No silent erosion under Phase-G.

4. **Remaining PARTIAL (#7 system metrics) is stable-deferred** — named v1.1 fix at `ml-diagnostics-draft.md §7 DL-GAP-2`; ~200 LOC `SystemMetricsCollector` + NVML probe does not block 1.0.0 per Round-4 residual-risk analysis. Not a Round-8 gating concern.

5. **Round-8 convergence condition.** If Round-7 synthesis reports clean on the other 7 personas (feasibility, spec-compliance, closure-verification, cross-spec-consistency, newbie-UX, senior-practitioner, TBD re-triage), industry parity is certified and the spec-set is ready for `/todos` → `/implement`. No structural spec edits required.

**Residual items carried forward from R4 (PERSIST, not Round-8 blockers):**

- `ml-notebook.md` stub still missing (R4 Residual Risk #2). 50-line acceptance criteria stub during the 1.0.0 wave.
- `km.quantize()` / `km.prune()` / `km.distill()` absent (R4 Residual Risk #3). Capability-flag matrix covers transitively via TRL/HF; v1.1 `ml-compression.md`.
- Cross-SDK fingerprint parity harness (`tests/integration/test_diagnostic_fingerprint_cross_sdk_parity.py` per ml-diagnostics `:909`) still unwritten (R4 Residual Risk #5). Zero industry-parity impact; wave-1 landing.

**Absolute paths consulted:**

- Output: `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-7-industry-parity.md`
- Baseline: `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-6-industry-parity.md` + `round-6-SYNTHESIS.md`
- Specs re-derived (all grep-verified 2026-04-21 post-Phase-G):
  - `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-*-draft.md` (17 files)
  - `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/supporting-specs-draft/*-integration-draft.md` (6 files)
  - `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/approved-decisions.md`

**Verdict:** Industry parity **stable at 24/25 GREEN** with 4× EXTENDED + 2× STRENGTHENED differentiators held. Phase-G is a clean pin — no new GREEN (ceiling unchanged), no regression, no weakening of any differentiator. §7.1.2 Single-Format-Per-Row Invariant specifically DOES NOT weaken the registry differentiator because the Python API stays dict-shaped and forward-compat-ready. Certify convergence on industry parity; recommend proceeding to Round-8 synthesis.
