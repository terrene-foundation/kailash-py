# Round-5 /redteam — Senior ML/DL/RL Practitioner Re-Audit (post-Phase-E)

Date: 2026-04-21
Auditor persona: Senior ML practitioner who has shipped ML platforms at scale (MLflow + Lightning + SB3 + TRL stack). Adoption bar unchanged: "I would stake my team's platform on this 1.0.0 spec."
Drafts audited: 15 under `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/*.md` (14,612 lines total, up from 14,025 in Round 4 — Phase-E landed ~587 net LOC of spec prose in `ml-engines-v2-draft.md` + `ml-engines-v2-addendum-draft.md` + `ml-registry-draft.md` + `ml-dashboard-draft.md` + 2 new draft files `ml-readme-quickstart-body-draft.md` + `ml-index-amendments-draft.md`).
Supporting specs audited: 6 under `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/supporting-specs-draft/`.
Prior rounds: Round-4 senior practitioner CERTIFIED with 1 NEW HIGH (A10-3 cross-spec drift) + 2 roadmap-appendix commitments (Section D/B binding to v1.1 labels).
Approved decisions: `04-validate/approved-decisions.md` (14 Decisions approved 2026-04-21).

**Verdict: CERTIFIED — A10-3 fully closed by Phase-E, Phase-E new surface integrates cleanly with senior-practitioner standards, ONE NEW MEDIUM finding at A11-NEW-1 (kaizen-ml sibling spec drift on `km.engine_info()` mandate), plus the TWO Round-4 roadmap-appendix commitments remain unfilled at spec level.**

Phase-E did ship. Of the 3 Round-4 residual items (A10-3 HIGH + 2 roadmap-appendix MEDIUMs), A10-3 is fully closed end-to-end (registry §5.6 produces, serving §2.5.1 consumes — verified by two-side grep below). The two roadmap-appendix items remain UNFILLED — `ml-engines-v2-draft.md §14` still lists only the architecture-family `v1.1-roadmap` label and does NOT bind the 6 Section-D Strategic Primitives (Model Card, quantization/pruning/distillation, ensemble registry, dataset version surface, explainability, cost dashboard, BYO-judge, OIDC/SAML) to a `kailash-ml/v1.1-strategic` label, nor bind the 7 Section-B edge cases to a `kailash-ml/v1.1-hardening` label. This remains acceptable under CERTIFIED per Round-4 language ("softer gap that I am willing to accept for CERTIFIED on the condition that the labels are filed before the first 1.0.0-rc") but warrants restated visibility.

The NEW MEDIUM finding at A11-NEW-1 is cross-spec drift introduced by Phase-E's new E11 Engine Registry surface — the addendum mandates that Kaizen agents obtain ML method signatures via `km.engine_info()`, but the companion `supporting-specs-draft/kaizen-ml-integration-draft.md` neither references `EngineInfo`/`km.engine_info()` nor binds the agent tool-discovery pattern. This is the same cross-spec drift pattern `rules/specs-authority.md §5b` exists to catch — Phase-E edited the addendum but the kaizen-ml integration sibling was not swept. Single-paragraph fix in the kaizen-ml integration spec closes it.

**Would I stake my team on kailash-ml 1.0.0 as specced NOW?** Yes — with ONE additional single-paragraph cross-spec fix (A11-NEW-1) AND the two Round-4 roadmap-binding commits before the first 1.0.0-rc tag. The 1.0.0 spine has zero load-bearing residuals; the remaining items are all either narrow cross-spec-drift fixes (A11-NEW-1, single paragraph) or intentional v1.1 deferrals awaiting label binding (Round-4 carry-over).

---

## Section A — 12 Spot Checks (Re-derived Against Current Spec State)

Status legend: **CLOSED** = Phase-E (and prior phases) landed the fix and cross-spec derivation confirms end-to-end coherence; **PARTIAL** = landed in some specs, drift in sibling; **OPEN** = not addressed; **EVOLVED** = fix is different from prior-round recommendation but equally or more defensible.

### A.1 Reproducibility Contract — **CLOSED (5/5)** — Phase-E Integration VERIFIED

No regressions from Round-4. `km.seed()` + `SeedReport` + 3-RNG RL checkpoint + feature-store BLAS-axis hash + `TrainingResult.seed_report` + `km.reproduce()` golden-run + `km.resume()` + `ModelCheckpoint` default-flip-to-True remain the spine. Phase-E integration verified:

- `km.seed` declared at `ml-engines-v2-draft.md §11.1 L1650-1674` as module-level function in `kailash_ml/__init__.py`.
- `km.reproduce` declared at `ml-engines-v2-draft.md §12 L1735-1763` as module-level async function.
- `km.resume` declared at `ml-engines-v2-draft.md §12A L1803-1835`.
- `km.lineage` (NEW Phase-E) declared at `ml-engines-v2-draft.md §15.8 L2163-2174` returning the canonical `LineageGraph` dataclass.
- `__all__` Group 1 ordering at `ml-engines-v2-draft.md §15.9 L2181-2197` pins the five module-level async functions in this order: `seed`, `reproduce`, `resume`, `lineage`, `rl_train`. Eager import mandate per zero-tolerance Rule 1a.
- Golden-run contract at §12.1 MUST 3 intact.

The Phase-E `km.lineage` addition slots cleanly into the reproducibility spine — it is the query-time surface that answers "what produced this model version" which is the natural extension of "what seed reproduced this run".

### A.2 Distributed Semantics — **CLOSED (5/5)**

No regressions. FSDP full-weight grad norm formula, ZeRO-3 `safe_get_local_fp32_param` path, Accelerate `PartialState` multi-axis rank gating, `DistributionEnv.{tp,pp,dp}_size`, cross-rank NaN broadcast all present and unchanged. Phase-E did not touch this zone.

### A.3 Numerical Stability — **CLOSED (5/5)**

A3-3 LATENCY_BUCKETS_MS still pinned at `ml-serving-draft.md §3.2.2` with 16-bucket set `(1, 5, 10, 25, 50, 100, 250, 500, 1_000, 2_500, 5_000, 10_000, 30_000, 60_000, 300_000, +Inf)` in milliseconds. Cardinality budget `16 × top-100 tenant × 2 model classes = 96 series/family` with `MetricCardinalityBudgetExceededError` gate. Tier-2 regression `test_inference_histogram_bucket_coverage.py`. No regression.

### A.4 Checkpoint + Resume Edge Cases — **CLOSED (5/5)**

Partial-epoch resume dedup, priority sum-tree persistence, HP-diff on resume, JSON-safety scope, `km.resume()` + `ModelCheckpoint` default all retained. Phase-E added no new clauses in this zone.

### A.5 RL Correctness — **CLOSED (4/4)**

Per-algo GAE defaults, n-step returns, `clip_range_vf` semantics, DPO reference-model temperature, `kl_from_reference` unified key all retained. No Phase-E changes.

### A.6 Classical ML — **CLOSED (4/4)**

Single-class split, Cook's + leverage + studentized residuals, clustering k-bounds, R² three-tier severity all present. No regression.

### A.7 LLM / Autolog — **CLOSED (4/4)**

A7-3 4-family streaming token-metric split at `ml-serving-draft.md §5.4` still pins `ml_inference_stream_first_token_latency_ms`, `ml_inference_stream_subsequent_token_latency_ms`, `ml_inference_stream_total_tokens_total`, `ml_inference_stream_duration_ms` with the emission contract at §5.4.2. No regression.

### A.8 Feature Store — **CLOSED (4/4)**

No regressions. Late-arrival policy, version immutability, training-serving skew, materialized_at index all present.

### A.9 AutoML — **CLOSED (3/3)**

No regressions. BOHB fidelity contract, ASHA rung-aware promotion, LLM token-level backpressure all present.

### A.10 Serving — **CLOSED (3/3) — A10-3 FULLY CLOSED BY PHASE-E E2**

Round-4's ONE HIGH was A10-3 cross-spec drift: serving-side ONNX custom-op handler referenced `ml-registry §4` for the producer contract but §4 was the Aliases chapter. Phase-E landed the producer contract at **`ml-registry-draft.md §5.6 "ONNX Export Probe"` (L221-255)** — verified end-to-end:

**Registry-side (producer)** — `ml-registry-draft.md §5.6`:

- §5.6.1 Probe Contract (MUST) — 4-step protocol at `register_model(format="onnx")`:
  1. Strict export via `torch.onnx.export(..., strict=True)` (permissive mode BLOCKED).
  2. On export failure, catch `torch.onnx.errors.UnsupportedOperatorError`, collect op names, populate `_kml_model_versions.onnx_unsupported_ops` as JSON array. Registration PROCEEDS (version row written) so serving can refuse with enumerated ops instead of crashing on partial artifact. WARN log `model_registry.onnx.unsupported_ops` with `model_name`, `version`, `unsupported_ops`, `tenant_id`.
  3. On export success, populate `_kml_model_versions.onnx_opset_imports` as `{domain: version}` JSONB.
  4. ort-extensions detection — when non-default opset domain present (`"com.microsoft"` etc.), populate `_kml_model_versions.ort_extensions` as JSON array of required package names.
- §5.6.2 `RegisterResult.onnx_status: Literal["clean", "legacy_pickle_only", "custom_ops"] | None` — 3-value ontology binds registry state to serving-side dispatch.
- §5A.2 Postgres DDL and §5A.3 SQLite variant both carry the 3 new columns `onnx_unsupported_ops JSONB`, `onnx_opset_imports JSONB`, `ort_extensions JSONB` (nullable; populated only when `format='onnx'`).
- §5A.4 Tier-2 test `test_model_registry_onnx_probe_wiring.py` — builds a registry row via `register_model(format="onnx")` against a torch model using FlashAttention-2; asserts `onnx_unsupported_ops` non-empty JSON array, WARN line emitted. Companion case: exportable model asserts `onnx_unsupported_ops IS NULL` AND `onnx_opset_imports` matches `ModelProto.opset_import`. Companion case for `ort_extensions`: model with `com.microsoft` custom-op domain populates required package names.

**Serving-side (consumer)** — `ml-serving-draft.md §2.5.1 L214-216`:

- Line 214: "Resolve `opset_imports` — the server pulls the `_kml_model_versions.onnx_opset_imports: dict[str, int]` column from the model registry (see `ml-registry-draft.md §5.6`)". Mismatch raises `OnnxOpsetMismatchError`.
- Line 215: "Register custom-op packages — for each name in the registry's `_kml_model_versions.ort_extensions` JSON list (populated by the probe in `ml-registry-draft.md §5.6`)". Missing packages raise `OnnxExtensionNotInstalledError`.
- Line 216: "If the model was tagged by the registry with `_kml_model_versions.onnx_unsupported_ops: list[str]` (non-empty — set when `register_model(format="onnx")` probed and recorded unsupported ops; see `ml-registry-draft.md §5.6`), the server MUST raise `OnnxExportUnsupportedOpsError` before touching the wire".
- Line 1185: Cross-reference binding registry §5.6 as producer, serving §2.5 as consumer.

**Mechanical verification** — I re-derived the cross-spec coherence by running three independent greps:

1. `grep 'onnx_unsupported_ops\|onnx_opset_imports\|ort_extensions' specs-draft/ml-registry-draft.md` → producer definitions present at L284-286 (DDL), L230-232 (probe contract), L247-249 (onnx_status ontology).
2. `grep 'onnx_unsupported_ops\|onnx_opset_imports\|ort_extensions' specs-draft/ml-serving-draft.md` → consumer references at L65 (ModelSignature field declaration), L214-216 (load-time resolver), L1185 (cross-reference).
3. `grep 'ml-registry-draft.md §5.6' specs-draft/ml-serving-draft.md` → 4 distinct back-references from consumer spec.

All three sides align. The A10-3 cross-spec drift is fully closed at spec level.

**This is senior-practitioner-grade.** The 3-value `onnx_status` ontology ("clean" / "custom_ops" / "legacy_pickle_only") is the correct partition — I've seen vendors collapse these three states into a single boolean and bite themselves when ort-extensions installation is a deployment step the vendor forgot to document. Naming the three states makes the downstream runbook tractable. Test coverage against FlashAttention-2 specifically is the right choice — that's the exact op that kept failing on silent-export in production ONNX deployments through 2024-25.

### A.11 Drift — **CLOSED (3/3)**

No regressions. Drift-type taxonomy, label lag, seasonal reference all present.

### A.12 Protocol Conformance — **CLOSED (4/4)**

No regressions. Shared `DiagnosticReport` shape, `f"{value:.17g}"` float serialization fingerprint, `adapter: ClassVar[str]` dispatch, sibling-spec forward-reference acknowledgment all present.

---

## Section A Summary

| Area                | Round-4 residuals            | R5 CLOSED | R5 PARTIAL | R5 OPEN | R5 NEW HIGH | R5 NEW MED        |
| ------------------- | ---------------------------- | --------- | ---------- | ------- | ----------- | ----------------- |
| A.1 Reproducibility | 0                            | 5         | 0          | 0       | 0           | 0                 |
| A.2 Distributed     | 0                            | 5         | 0          | 0       | 0           | 0                 |
| A.3 Numerical       | 0                            | 5         | 0          | 0       | 0           | 0                 |
| A.4 Checkpoint      | 0                            | 5         | 0          | 0       | 0           | 0                 |
| A.5 RL              | 0                            | 4         | 0          | 0       | 0           | 0                 |
| A.6 Classical       | 0                            | 4         | 0          | 0       | 0           | 0                 |
| A.7 Autolog         | 0                            | 4         | 0          | 0       | 0           | 0                 |
| A.8 Feature Store   | 0                            | 4         | 0          | 0       | 0           | 0                 |
| A.9 AutoML          | 0                            | 3         | 0          | 0       | 0           | 0                 |
| A.10 Serving        | 1 HIGH (A10-3)               | 3         | 0          | 0       | 0           | 0                 |
| A.11 Drift          | 0                            | 3         | 0          | 0       | 0           | **1 (A11-NEW-1)** |
| A.12 Protocol       | 0                            | 4         | 0          | 0       | 0           | 0                 |
| **Total**           | **1 HIGH + 2 MED carryover** | **49**    | **0**      | **0**   | **0**       | **1 new MED**     |

**Net:** Round-4 had 1 HIGH + 2 MED carryovers; Round-5 closes the HIGH (A10-3) at spec-level and surfaces ONE new MED cross-spec drift finding (A11-NEW-1 — kaizen-ml integration drift on new E11 agent tool discovery mandate). No new HIGH. The two Round-4 roadmap-binding commitments remain unfilled at spec level.

---

## Section B — 15 Edge Cases (Retained From Round 3-4)

No material change from Round-4. 6 CLOSED, 2 PARTIAL, 7 OPEN — the 7 OPEN items remain appropriate v1.1 hardening work. Phase-E did NOT add an explicit "v1.1 Hardening Roadmap" appendix binding these to a milestone label (`kailash-ml/v1.1-hardening`). This is Round-4 commit #3 carried over unchanged. Restated as Round-5 MED carryover.

---

## Section C — 2026-27 Architectures

No regression from Round-4: 2 SUPPORTED, 4 PARTIAL, 2 ADAPTER (sufficient for 1.0 training via generic Lightning), 4 DEFERRED with named extension points, 0 FAIL. `ml-engines-v2-draft.md §14 Future-Proofing` still has the short roadmap table; the DEFERRED items bind to `kailash-ml/v1.1-roadmap` label at L1937 in prose. I did NOT verify the GitHub label exists (out of audit scope); strongly advise filing the milestone issues before the 1.0.0-rc tag.

---

## Section D — Strategic Primitives

No material change from Round-4: 8 CLOSED (reproduce, multi-run comparison, golden run, fairness, calibration, uncertainty, continual learning, AutoML leaderboard), 1 PARTIAL (dataset versioning via hash without public `DatasetVersion` surface), 6 OPEN (Model Card export primitive, quantization/pruning/distillation, ensemble per-component registry, inference-time explainability, cost dashboarding/`cost_usd` on `TrainingResult`, BYO-judge evaluation leaderboard, identity-provider binding for `actor_id`).

For the THIRD time across three rounds (R3 senior, R4 senior, R5 senior), the specs do NOT contain an explicit "v1.1 Strategic Roadmap" appendix binding these 6 OPEN primitives to named milestone issues under label `kailash-ml/v1.1-strategic`. Round-4 flagged this as a ~30-minute commit (40 lines across `ml-engines-v2-draft.md §14` + `ml-serving-draft.md §11`); Phase-E did not land it. Restated as Round-5 MED carryover.

**Phase-E new surface integration verified:**

- `LineageGraph` / `LineageNode` / `LineageEdge` frozen dataclasses declared at `ml-engines-v2-addendum-draft.md §E10.2 L358-412` — tenant-scoped (every `LineageNode.tenant_id` required, cross-tenant reads raise `CrossTenantReadError`), depth-bounded (`max_depth: int = 10` guards cyclic and deep graphs), 5 node kinds × 6 edge relations with typed `Literal[...]` constraints. This is the canonical shape; `ml-dashboard-draft.md §4.1.1 L169-174` explicitly imports it ("This spec does NOT redefine the shape — redefinition is a HIGH finding under `rules/specs-authority.md §5b`") and `ml-engines-v2-draft.md §15.8 L2163-2174` references it as the return type of `km.lineage`. No drift across the 4 spec files touching lineage.
- `ParamSpec` / `MethodSignature` / `EngineInfo` frozen dataclasses declared at `ml-engines-v2-addendum-draft.md §E11.1 L450-492` — the Engine Registry surface for agent tool discovery. Includes `is_deprecated` / `deprecated_since` / `deprecated_removal` on `MethodSignature` for deprecation tracking, `accepts_tenant_id` / `emits_to_tracker` / `clearance_level` on `EngineInfo` for PACT + tenant wiring visibility, `extras_required` for declared-extras discovery, `version` MUST equal `kailash_ml.__version__` atomically (zero-tolerance Rule 5 binding). Tier-2 wiring test `test_engine_registry_signature_discovery.py` asserts all 13 engines registered with exactly 8 MethodSignature entries per Decision 8.

These 6 new frozen dataclasses are fully typed, hashable (safe to cache in agent tool descriptors), and integrate cleanly with the existing Engine spine. The reproducibility story (km.seed + km.reproduce + golden-run + km.resume + km.lineage) is intact AND extended by Phase-E — `km.lineage` is the natural "what produced this model" query-time surface pairing to the "how to reproduce" runtime surface of `km.seed` + `km.reproduce`.

---

## Section E — Certification Statement

### Would I stake my team on kailash-ml 1.0.0 as specced NOW?

**With ONE single-paragraph cross-spec fix (A11-NEW-1) + the two Round-4 roadmap-appendix commits before the 1.0.0-rc tag: YES.**

**Without those three fixes: YES for the spine, NO for the full release envelope.** A11-NEW-1 is a cross-spec drift in a NEW surface Phase-E introduced — the addendum §E11.3 MUST 1 says "Kaizen agents that call ML functionality MUST obtain the method signatures via `km.engine_info()`" but the companion `supporting-specs-draft/kaizen-ml-integration-draft.md` does not reference `EngineInfo`, `km.engine_info()`, or the agent tool-discovery pattern at all. This is the same cross-spec drift pattern `rules/specs-authority.md §5b` was written to prevent, and it is a MED finding (lower severity than A10-3 was because the kaizen-ml integration spec is a supporting spec, not a core ML spec — but the mechanical coherence requirement is the same). The fix is a ~1-paragraph addition to kaizen-ml-integration §2.3 (or a new §2.4) referencing the E11 surface and binding the agent tool-discovery pattern.

### What changed Round 4 → Round 5

- **1 HIGH (A10-3) + 2 MED carryovers → 1 NEW MED (A11-NEW-1) + 2 MED carryovers (unchanged).** Phase-E landed everything the Round-4 prompt pre-flagged: A10-3 producer contract at registry §5.6 (with DDL columns, 3-value onnx_status ontology, Tier-2 probe wiring test, 4-step probe protocol), 2 new addendum enrichments (E10 Cross-Engine Lineage + E11 Engine Registry) with 6 new frozen dataclasses, `km.lineage` module-level async function, `km.engine_info`/`km.list_engines` module-level helpers, Quick Start SHA-pin fingerprint contract (verified byte-for-byte: SHA256 `c962060cf467cc732df355ec9e1212cfb0d7534a3eed4480b511adad5a9ceb00`, 246 bytes, 6 non-blank lines), `ml-index-amendments-draft.md` + `ml-readme-quickstart-body-draft.md` as Phase-E authored artifacts for the /codify gate.
- **Spec size grew 14,025 → 14,612 LOC (+587, +4.2%).** Growth concentrated in the addendum (510 → 670 LOC, +160), ml-dashboard (772 → 810 LOC, +38 for the lineage REST endpoint + canonical LineageGraph binding), ml-registry (1027 → 1067 LOC, +40 for the §5.6 ONNX probe + DDL columns + Tier-2 probe wiring test), ml-engines-v2 (2423 → 2473 LOC, +50 for §15.8 km.lineage + §15.9 **all** Group 1 extension), plus 2 new files (`ml-index-amendments-draft.md` 183 LOC + `ml-readme-quickstart-body-draft.md` 116 LOC). Growth is senior-practitioner-legible — no filler, every new clause names a contract.
- **New Phase-E strengths:** the `LineageGraph` + `LineageNode` + `LineageEdge` shape is the right partition (5 node kinds, 6 edge relations, tenant-scoped, depth-bounded); the `EngineInfo` + `MethodSignature` + `ParamSpec` shape with `is_deprecated` / `deprecated_since` / `deprecated_removal` on MethodSignature is senior-grade (deprecation tracking was absent from Round-4 spec and is a classic gap in MLflow/W&B registries); the `RegisterResult.onnx_status` 3-value ontology ("clean" / "custom_ops" / "legacy_pickle_only") correctly partitions the ONNX deployment state space; the Quick Start SHA-pin at 246 bytes / 6 lines delivers the 5-line newbie promise (§16.2 MUST 1 bounds 5-10 non-blank lines inclusive).

### What's left for CERTIFIED

Three fixes, total ~2.5 hours of spec work:

1. **A11-NEW-1 cross-spec fix** (~30 min) — add §2.4 "Agent Tool Discovery via `km.engine_info()`" to `supporting-specs-draft/kaizen-ml-integration-draft.md`. Define:
   - The E11.3 MUST 1 mandate binds: Kaizen agents ingesting ML functionality MUST call `km.list_engines()` at agent-init time to obtain the `tuple[EngineInfo, ...]` and MUST use each `EngineInfo.signatures` tuple to derive the tool descriptors.
   - The addendum imports: `from kailash_ml import list_engines, engine_info, EngineInfo, MethodSignature, ParamSpec`.
   - Tier-2 wiring test binding: `tests/integration/test_kaizen_agent_ml_tool_discovery_wiring.py` asserts a Kaizen agent bootstrapped against `km.list_engines()` produces exactly 13 × 8 = 104 tool descriptors (13 engines × 8-method surface).
   - Cross-reference: `ml-engines-v2-addendum-draft.md §E11.3 MUST 1` as the authoritative mandate.
2. **v1.1 Strategic Primitives roadmap appendix** (~30 min) — Round-4 commit #2 carried over unchanged. Add explicit appendix in `ml-engines-v2-draft.md §14` binding the 6 OPEN Section-D primitives (Model Card, quantization/pruning/distillation, ensemble registry, `DatasetVersion` public surface, inference-time explainability, cost dashboard / `cost_usd` on `TrainingResult`, BYO-judge leaderboard, OIDC/SAML `actor_id` identity-provider binding) to milestone label `kailash-ml/v1.1-strategic` with one-paragraph spec intent per item.
3. **v1.1 Hardening roadmap appendix** (~30 min) — Round-4 commit #3 carried over unchanged. Add explicit appendix binding the 7 OPEN Section-B edge cases (warm-restart LR indexing, dataloader persistent_workers contextvar, read-replica RYW, drift schema mismatch, SDK-upgrade DL checkpoint migration, deleted-artifact leaderboard, spot-preemption heartbeat, WS multi-frame prompt accumulation, attested-determinism cache) to `kailash-ml/v1.1-hardening` with one-sentence spec intent per item.

All 3 items together are ~1.5 hours of spec work. After landing, I would stake my team on kailash-ml 1.0.0.

### Persona-specific parting judgment — stake-the-team verdict

Round 1 → Round 5 is five consecutive rounds where the spec authors took each round's audit list, did not defer items to "future session", and closed the pre-flagged findings. Phase-E is stronger than Phase-D because:

- The A10-3 closure is **end-to-end verified, not one-sided** — Phase-D closed A10-3 at the serving side (§2.5.1) but the registry-side producer contract drifted; Phase-E not only landed the producer contract at §5.6 but also added `RegisterResult.onnx_status` as a typed Literal ontology AND DDL columns AND Tier-2 probe wiring test, closing the full cross-spec loop.
- The **new Phase-E surface (km.lineage + EngineInfo + MethodSignature + ParamSpec + LineageGraph + LineageNode + LineageEdge)** is not just additive — it is integrated with existing Engine spine contracts. `EngineInfo.version` binds to zero-tolerance Rule 5 atomicity. `EngineInfo.accepts_tenant_id` / `emits_to_tracker` / `clearance_level` surface the tenant + tracker + PACT invariants to agents at discovery time. `LineageNode.tenant_id` is required (never None) per `rules/tenant-isolation.md`. `MethodSignature.is_deprecated` provides a deprecation-tracking surface that every competitor (MLflow, W&B, Neptune, Comet, ClearML) lacks.
- The **Quick Start SHA-pin** is the correct structural defense against documentation drift. Verified byte-for-byte reproducible: `python3 -c "import hashlib; canonical = '...'; print(hashlib.sha256(canonical.encode()).hexdigest())"` yields `c962060cf467cc732df355ec9e1212cfb0d7534a3eed4480b511adad5a9ceb00` matching the spec. A README that drifts fails CI at the regression-test gate; a README that matches is the single-source-of-truth for every downstream blog / Stack Overflow / one-liner.
- The **one cross-spec drift that slipped through (A11-NEW-1)** is a narrow, named, single-paragraph fix at a supporting spec. It is the "long tail" of cross-spec drift that `rules/specs-authority.md §5b` exists to catch; the audit caught it; the fix is mechanical. This is lower severity than A10-3 was — A10-3 was a contract whose consumer promised behavior the producer did not deliver; A11-NEW-1 is a MUST-mandate on a sibling spec that was not swept when the mandate landed. Both are structural drift, but the user-facing blast radius differs (A10-3 would have crashed a production FlashAttention-2 serving deployment; A11-NEW-1 would mean Kaizen agents hard-code ML method signatures at agent-authoring time instead of discovering them, which is an operational-ceremony defect, not a runtime crash).

The remaining two Round-4 carryovers (v1.1 strategic + v1.1 hardening roadmap appendices) are commitment-gate items, not capability-gate items. Three rounds in a row the specs have declined to file them. My recommendation remains: file them before the 1.0.0-rc tag. Filing the labels converts "we will ship this later" into "we have filed public issues that the community can track", which is the difference between a promise and a contract. For a 1.0.0 release that advertises API stability, the contract form is required.

**Verdict: CERTIFIED — stake-the-team verdict is YES conditional on the 3 fixes above landing in one shard before the first 1.0.0-rc tag.** That is the single-session gap between current spec state and a release I would put into production. The 1.0.0 spine is production-ready. A11-NEW-1 + 2 roadmap-binding appendices = ~1.5 hours of spec work = one short shard.

---

## Section F — NEW MED Finding: A11-NEW-1 Cross-Spec Drift on E11 Agent Tool Discovery

**Severity:** MEDIUM (cross-spec drift per `rules/specs-authority.md §5b`). Lower than A10-3 was (HIGH) because the affected sibling is a supporting integration spec, not a core ML spec, and the user-facing blast radius is operational rather than runtime.

**Scope:** `specs-draft/ml-engines-v2-addendum-draft.md §E11.3 MUST 1` (producer) AND `supporting-specs-draft/kaizen-ml-integration-draft.md` (consumer — sibling spec that was not swept).

**Finding.** The Phase-E E11 Engine Registry surface at `ml-engines-v2-addendum-draft.md §E11.3 MUST 1 L557-559` says:

> "Kaizen agents that call ML functionality MUST obtain the method signatures via `km.engine_info()`, not hard-coded imports. This keeps agent tool contracts in sync with the Engine API surface automatically."

The cited sibling spec `supporting-specs-draft/kaizen-ml-integration-draft.md` (430 lines, covering Kaizen × kailash-ml integration for the 2.12.0 release) has **zero grep hits for** `EngineInfo`, `MethodSignature`, `ParamSpec`, `km.list_engines`, `km.engine_info`, `km.lineage`, or `LineageGraph`. The spec covers:

- §2: `tracker=` kwarg on every diagnostic adapter (3 adapters × `Optional[ExperimentRun]` kwarg).
- §3 (implied from outline): Shared CostTracker wire format (microdollars).
- §4: TraceExporter → shared SQLite store.

No section covers the agent tool-discovery pattern that E11.3 MUST 1 mandates Kaizen implement. The consumer side of the E11 contract is undefined at the sibling-spec level.

**Why this is MED (not HIGH).** The A11-NEW-1 mismatch does not cause a runtime crash at 1.0.0:

- If the Kaizen integration lands without the E11 binding, agents hard-code ML tool descriptors at authoring time (the status quo). Agents work.
- When the ML API surface evolves (a new `MLEngine` method, a signature change on `TrainingPipeline.train`), agents silently diverge from the live ML API until the agent author hand-updates the descriptors.
- This is a staleness defect, not a correctness defect — contrast with A10-3 which would have crashed a FlashAttention-2 serving deployment on first request.

The user-facing cost is: agents that were meant to be "automatically in sync with the Engine API surface" (the E11.3 MUST 1 promise) are in fact manually in sync until a human catches the drift. That is a real promise breakage, but it is operational-ceremony-level, not runtime-crash-level — hence MED.

**Recommended fix (~30 min).** Add a new subsection `§2.4 "Agent Tool Discovery via km.engine_info()"` to `supporting-specs-draft/kaizen-ml-integration-draft.md`. Define:

```markdown
### 2.4 Agent Tool Discovery via km.engine_info()

Binds `ml-engines-v2-addendum-draft.md §E11.3 MUST 1`: Kaizen agents ingesting ML
functionality MUST obtain ML tool descriptors from `km.list_engines()` /
`km.engine_info(name)` at agent-init time rather than hard-coding imports from
`kailash_ml.engines.*`.

#### Contract (MUST)

1. At Kaizen agent initialization, call `km.list_engines()` to obtain
   `tuple[EngineInfo, ...]` from the authoritative registry.
2. For each `EngineInfo`, iterate `signatures: tuple[MethodSignature, ...]` to
   derive tool descriptors. The 8-method surface per engine (per Decision 8 /
   `ml-engines-v2-draft.md §2.1 MUST 5`) produces 13 × 8 = 104 tool descriptors
   baseline.
3. Skip any `MethodSignature` where `is_deprecated=True` UNLESS the agent's
   config explicitly opts into deprecated surfaces via
   `include_deprecated_ml_tools=True`.
4. Refresh `km.list_engines()` when kailash-ml is upgraded — the `EngineInfo.version`
   field (atomically bound to `kailash_ml.__version__` per zero-tolerance Rule 5)
   is the refresh trigger.

#### Tier-2 Wiring Test

`packages/kailash-kaizen/tests/integration/test_agent_ml_tool_discovery_wiring.py` —
bootstraps a Kaizen agent against a fresh `km.list_engines()` result; asserts
the produced tool descriptor count equals 13 × 8 = 104 (after filtering deprecated
signatures, assuming none are deprecated at 1.0.0).

#### Cross-References

- `ml-engines-v2-addendum-draft.md §E11.3 MUST 1` — authoritative producer
  mandate that this section binds.
- `ml-engines-v2-addendum-draft.md §E11.1` — `EngineInfo` / `MethodSignature`
  / `ParamSpec` canonical dataclass declarations.
- `rules/zero-tolerance.md Rule 5` — `EngineInfo.version` atomicity.
```

After this paragraph lands, A11-NEW-1 is closed and the E11 contract has a consumer-side binding in the sibling spec. The mechanical coherence check (`grep 'EngineInfo\|km.engine_info\|km.list_engines' supporting-specs-draft/kaizen-ml-integration-draft.md`) will return 5+ hits, confirming the cross-spec sweep.

---

## Roadmap-Binding Carryover (Unchanged From Round-4)

Repeated for spec-authority visibility. Round-4 flagged two roadmap-appendix items as "softer gap acceptable for CERTIFIED on the condition that the labels are filed before the first 1.0.0-rc". Phase-E did not land either. Round-5 restates the ask:

1. **v1.1 Strategic Primitives roadmap appendix** (~30 min) — `ml-engines-v2-draft.md §14` addendum binding the 6 Section-D OPEN primitives to milestone label `kailash-ml/v1.1-strategic`.
2. **v1.1 Hardening roadmap appendix** (~30 min) — `ml-engines-v2-draft.md §14` addendum binding the 7 Section-B OPEN edge cases to milestone label `kailash-ml/v1.1-hardening`.

Both convert prose-level "we will ship this later" into filed public issues the community can track. For a 1.0.0 release advertising API stability, the label-bound form is the contract form. Deferring these a third time is the institutional ratchet `rules/zero-tolerance.md` Rule 1 exists to prevent. The filing cost is ~1 hour total; the cost of NOT filing is a downstream consumer asking "when is Model Card coming?" and having no public issue to link to.

---

## Findings file (absolute path)

`/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-5-senior-practitioner.md`

## Drafts audited (absolute paths, 15 + 2 Phase-E new artifacts)

- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-autolog-draft.md` (690 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-automl-draft.md` (650 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-backends-draft.md` (659 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-dashboard-draft.md` (810 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-diagnostics-draft.md` (1070 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-drift-draft.md` (885 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-engines-v2-addendum-draft.md` (670 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-engines-v2-draft.md` (2473 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-feature-store-draft.md` (732 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-index-amendments-draft.md` (183 lines — Phase-E new)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-readme-quickstart-body-draft.md` (116 lines — Phase-E new)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-registry-draft.md` (1067 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-rl-algorithms-draft.md` (464 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-rl-align-unification-draft.md` (429 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-rl-core-draft.md` (1234 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-serving-draft.md` (1214 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-tracking-draft.md` (1266 lines)

Supporting specs:

- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/supporting-specs-draft/align-ml-integration-draft.md` (356 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/supporting-specs-draft/dataflow-ml-integration-draft.md` (343 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/supporting-specs-draft/kailash-core-ml-integration-draft.md` (594 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/supporting-specs-draft/kaizen-ml-integration-draft.md` (430 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/supporting-specs-draft/nexus-ml-integration-draft.md` (364 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/supporting-specs-draft/pact-ml-integration-draft.md` (367 lines)

Total: 14,612 + 2,454 = 17,066 lines audited. Verification commands executed per `rules/testing.md` audit-mode re-derivation rule (no prior-round outputs cached; every Phase-E closure re-derived at audit time, including the Quick Start SHA-256 fingerprint re-computation yielding byte-for-byte match with the spec-embedded constant).
