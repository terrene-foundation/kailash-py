# Round 6 Senior Practitioner Verdict

**Date:** 2026-04-21
**Persona:** 10+ yr MLOps, shipped production registries + feature stores (MLflow + Feast + Lightning + W&B)
**Verdict:** **CERTIFIED** — A11-NEW-1 closed by Phase-F F4, F3 RegisterResult/artifact_uris is practitioner-grade, F5 km.lineage signature is right, F6 ClearanceRequirement triple is a genuine improvement. ONE new MED finding (engine-count drift between §E1.1 / §E11.3 MUST 4 / §2.4.7) plus two Round-4 roadmap carryovers unchanged.

Rubric re-derived from scratch against current spec state. Every line number below re-greped at audit time; Phase-F edits shifted numbering in ml-engines-v2-draft (now 2473 LOC), ml-engines-v2-addendum (now ~700 LOC), ml-registry-draft (now 1067 LOC), kaizen-ml-integration (now ~600 LOC).

---

## Rubric (29 items)

| ID      | Item                                                                                      | R5                    | R6                                       | file:line                                                                                   | Note                                                                                                                                                                                                                                                                             |
| ------- | ----------------------------------------------------------------------------------------- | --------------------- | ---------------------------------------- | ------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A1**  | `MLEngine` eight-method surface frozen                                                    | CLOSED                | CLOSED                                   | ml-engines-v2-draft.md:213-215, :2277                                                       | `setup, compare, fit, predict, finalize, evaluate, register, serve`. §15.10 explicit restatement. Practitioner: right.                                                                                                                                                           |
| **A2**  | `Trainable` protocol + Lightning adapter                                                  | CLOSED                | CLOSED                                   | ml-engines-v2-draft.md:§3 (L456-1082)                                                       | Pairs with HuggingFace adapter at L946. Right partition.                                                                                                                                                                                                                         |
| **A3**  | `TrainingResult` canonical dataclass                                                      | CLOSED                | CLOSED                                   | ml-engines-v2-draft.md:§4.1 (L1087-1127)                                                    | 8 required fields; `device` + `lightning_trainer_config` both load-bearing. No drift.                                                                                                                                                                                            |
| **A4**  | Multi-tenant propagation (tenant_id required)                                             | CLOSED                | CLOSED                                   | ml-engines-v2-draft.md:§5 (L1202-1304), addendum §E3 (L145-169)                             | `TenantRequiredError` on missing. E3.1 MUST 1 flows `MLEngine(tenant_id="acme")` into every sub-primitive.                                                                                                                                                                       |
| **A5**  | ONNX-default artifacts                                                                    | CLOSED                | CLOSED                                   | ml-engines-v2-draft.md:§6 (L1304-1400)                                                      | Feeds §7.1 `artifact_uris["onnx"]` priority. Paired with registry §5.6 probe.                                                                                                                                                                                                    |
| **A6**  | PyCaret/MLflow-better claim-to-test mapping                                               | CLOSED                | CLOSED                                   | ml-engines-v2-draft.md:§7.2 (L1447-1461), addendum §E13.1 (L633-650)                        | E13.1 is the merge-gate E2E. 13-step flow, specific enough to block regressions.                                                                                                                                                                                                 |
| **A7**  | `km.*` wrapper surface + `__all__` ordering                                               | CLOSED                | CLOSED                                   | ml-engines-v2-draft.md:§15.9 (L2181-2239)                                                   | 6-group partition, Group 6 added for `engine_info` + `list_engines`. Eager imports at L2245-2263 (CodeQL-clean).                                                                                                                                                                 |
| **A8**  | `km.seed` + `km.reproduce` + `km.resume`                                                  | CLOSED                | CLOSED                                   | ml-engines-v2-draft.md:§11, §12, §12A (L1640-1870)                                          | Three module-level async functions; all at module scope in `__init__.py` (no lazy `__getattr__`).                                                                                                                                                                                |
| **A9**  | `km.lineage` wrapper                                                                      | CLOSED (divergent)    | **CLOSED (fixed)**                       | ml-engines-v2-draft.md:§15.8 (L2163-2176), addendum §E10.3 MUST 1 (L418)                    | F5 flipped `tenant_id` from required to `Optional[str] = None` with ambient resolution via `get_current_tenant_id()`. Matches every sibling km.\* verb.                                                                                                                          |
| **A10** | Cross-engine lineage graph (`LineageGraph` dataclass)                                     | CLOSED                | CLOSED                                   | addendum §E10.2 (L358-412)                                                                  | 5 node kinds × 6 edge relations; tenant_id required (never None); `max_depth=10`. ml-dashboard §4.1.1 (L169-174, L205) imports canonical shape explicitly.                                                                                                                       |
| **A11** | Engine Registry (`EngineInfo` + `MethodSignature` + `ParamSpec` + `ClearanceRequirement`) | 1 NEW MED (A11-NEW-1) | **CLOSED (A11-NEW-1 closed; 1 NEW MED)** | addendum §E11.1 (L450-518), §E11.2 (L562-582), §E11.3 (L584-603); kaizen-ml §2.4 (L126-303) | F4 landed §2.4 (8 subsections, ~170 LOC). F6 replaced flat `Literal["D","T","R","DTR"]` with `ClearanceRequirement(axis, min_level)` tuple. **NEW finding below (A11-NEW-2).**                                                                                                   |
| **T1**  | `km.track` + contextvar-based ambient run                                                 | CLOSED                | CLOSED                                   | ml-tracking-draft.md:§2, §10.1, §10.2 (L1029-1031)                                          | `get_current_run()` + `get_current_tenant_id()` public accessors, `_current_run` direct access BLOCKED.                                                                                                                                                                          |
| **T2**  | `ExperimentTracker` engine + `ExperimentRun`                                              | CLOSED                | CLOSED                                   | ml-tracking-draft.md:§3-§6                                                                  | 8 tables all prefixed `_kml_*` (per F1 DDL unification — verified via grep).                                                                                                                                                                                                     |
| **T3**  | `TrainingResult.tracker_run_id` + 18-engine auto-wire                                     | CLOSED                | CLOSED                                   | addendum §E1.1 (L24-41), §E1.2 MUST 1 (L47-74)                                              | 18/18 engines auto-wire. `kailash_ml.tracking.get_current_run()` is the ambient read.                                                                                                                                                                                            |
| **T4**  | `km.autolog` + framework auto-instrumentation                                             | CLOSED                | CLOSED                                   | ml-autolog-draft.md:§2, ml-engines-v2-draft.md:§15.8 (L2160)                                | Reuses the shared contextvar accessor. No independent global.                                                                                                                                                                                                                    |
| **T5**  | Reproduction + golden-run path                                                            | CLOSED                | CLOSED                                   | ml-engines-v2-draft.md:§12.1 MUST 3, ml-registry-draft.md:§7.5 (L581-680)                   | `km.reproduce()` resolves `is_golden` lineage. Tier-3 gold-run regression test specified.                                                                                                                                                                                        |
| **R1**  | Single `ModelRegistry` (two-registry collapse)                                            | CLOSED                | CLOSED                                   | ml-registry-draft.md:§2.1-§2.4 (L41-84)                                                     | Decision 5 pinned. Two-registry drift resolved.                                                                                                                                                                                                                                  |
| **R2**  | `RegisterResult` canonical dataclass (field shape)                                        | 1 HIGH (R5-1)         | **CLOSED**                               | ml-registry-draft.md:§7.1 (L413-447)                                                        | F3 flipped `artifact_uri: str` → `artifact_uris: dict[str, str]`. `onnx_status: Optional[Literal[...]]` added at L429. Deprecation shim via `@property` at §7.1.1 (L448-479) retains `result.artifact_uri` for v1.x (returns `artifact_uris["onnx"]`, emits DeprecationWarning). |
| **R3**  | Integer-monotonic versions + aliases                                                      | CLOSED                | CLOSED                                   | ml-registry-draft.md:§3.2, §4 (L98-195)                                                     | Alias atomicity (§4.1 MUST 3) + tenant-scoped (§4.2). Soft-delete per §4.1 MUST 5.                                                                                                                                                                                               |
| **R4**  | Content-addressed artifact store + per-tenant quotas                                      | CLOSED                | CLOSED                                   | ml-registry-draft.md:§10 (L828-873)                                                         | `cas://sha256:<hex>` URI scheme; `_kml_model_versions.artifact_uri` column per DDL §5A.2.                                                                                                                                                                                        |
| **R5**  | ONNX export probe (`onnx_status` 3-value ontology)                                        | CLOSED                | CLOSED                                   | ml-registry-draft.md:§5.6 (L221-250)                                                        | 4-step probe, `onnx_unsupported_ops` + `onnx_opset_imports` + `ort_extensions` all persisted. Paired with serving §2.5.1 cross-spec loop (A10 closure).                                                                                                                          |
| **S1**  | `InferenceServer` multi-channel serve                                                     | CLOSED                | CLOSED                                   | ml-serving-draft.md:§2 (channels=[...])                                                     | `rest` / `grpc` / `websocket` all first-class.                                                                                                                                                                                                                                   |
| **S2**  | ONNX consumer resolution (opset + ort-extensions)                                         | CLOSED                | CLOSED                                   | ml-serving-draft.md:§2.5.1 (L214-216), L1185                                                | Reads `_kml_model_versions.onnx_opset_imports` + `.ort_extensions` + `.onnx_unsupported_ops`. Typed errors per column.                                                                                                                                                           |
| **S3**  | Shadow traffic + canary deployment                                                        | CLOSED                | CLOSED                                   | ml-serving-draft.md:§2.4 (`predict_with_shadow`), addendum §E1.1 row                        | Emission to shared tracker per E1.2 MUST 1.                                                                                                                                                                                                                                      |
| **S4**  | Inference metric cardinality budget                                                       | CLOSED                | CLOSED                                   | ml-serving-draft.md:§3.2.2 (16-bucket histogram, 96 series/family)                          | `MetricCardinalityBudgetExceededError` gate. Regression test named.                                                                                                                                                                                                              |
| **F1**  | FeatureStore late-arrival + version immutability                                          | CLOSED                | CLOSED                                   | ml-feature-store-draft.md:§3 (version), §4 (late-arrival)                                   |                                                                                                                                                                                                                                                                                  |
| **F2**  | Training-serving skew hash                                                                | CLOSED                | CLOSED                                   | ml-feature-store-draft.md:§5 (BLAS-axis hash)                                               | Surfaces in `TrainingResult.feature_versions`.                                                                                                                                                                                                                                   |
| **F3**  | Feature materialization (`materialized_at` index)                                         | CLOSED                | CLOSED                                   | ml-feature-store-draft.md:§6                                                                |                                                                                                                                                                                                                                                                                  |
| **F4**  | `FeatureStore.erase_tenant()` PACT-gated                                                  | CLOSED                | CLOSED                                   | addendum §E9.2 (L326, `FeatureStore.erase_tenant()` = D:H, T:H, R:Human)                    | Cleanly slots into F6 `ClearanceRequirement` shape.                                                                                                                                                                                                                              |
| **D1**  | `DriftMonitor` drift-type taxonomy                                                        | CLOSED                | CLOSED                                   | ml-drift-draft.md:§3                                                                        |                                                                                                                                                                                                                                                                                  |
| **D2**  | Diagnostics adapters (DL/RAG/RL)                                                          | CLOSED                | CLOSED                                   | ml-diagnostics-draft.md:§3, ml-engines-v2-draft.md:§15.8 (L2158)                            |                                                                                                                                                                                                                                                                                  |
| **D3**  | Dashboard REST + SSE + lineage endpoint                                                   | CLOSED                | CLOSED                                   | ml-dashboard-draft.md:§4.1 (L149-163), §4.1.1 (L169-207)                                    | `/api/v1/lineage/{run_id}` returns canonical `LineageGraph` JSON via `dataclasses.asdict()`.                                                                                                                                                                                     |

**Totals:** 29/29 items CLOSED. Down from R5 (28/29 + 1 NEW MED). One new finding surfaces **A11-NEW-2** (see below) but it does not downgrade A11 to OPEN — the E11 contract as declared is correct, the finding is an internal cross-reference inconsistency within the addendum.

---

## What closed this round

**F3 (R2 / HIGH-R5-1 from Round 5)** — `RegisterResult.artifact_uris: dict[str, str]` is now canonical. A senior practitioner ships with a dict keyed by format because (a) ONNX-first registration still leaves a pickle fallback on failure; (b) dual-format emission (ONNX + TorchScript for different consumer profiles) is a production reality at every company I've shipped at; (c) the deprecation shim at §7.1.1 retains `result.artifact_uri` as a `@property` emitting `DeprecationWarning` and returning `artifact_uris["onnx"]` — this is the correct legacy sunset (v1.x shim, removed at v2.0, no field-level `str` that could pickle-drift across version boundaries). Decision 11 is cleanly specced.

**F4 (A11-NEW-1 from Round 5)** — `supporting-specs-draft/kaizen-ml-integration-draft.md §2.4` landed with 8 subsections covering (1) the MUST mandate binding E11.3 MUST 1, (2) re-imports from the authoritative declaration (NOT redefinition — cross-spec drift avoided per §5b), (3) the `EngineInfo` field table with annotations, (4) tenant-scoped lookup via PACT envelope filtering, (5) version-sync invariant binding §E11.3 MUST 3, (6) BLOCKED-pattern section with 5 rationalization guards, (7) worked example of `MLAwareAgent` subclass, (8) Tier-2 wiring test. The spec says exactly what a senior Kaizen engineer needs to implement: `km.list_engines()` + `km.engine_info(name)` at agent init, traverse `EngineInfo.signatures`, filter by `clearance_level` against PACT envelope, skip `is_deprecated=True` unless opted in, refresh on `__version__` bump. **Senior-grade.**

**F5 (L-1 from Round 5)** — `km.lineage(..., tenant_id: str | None = None, max_depth: int = 10)` at ml-engines-v2-draft §15.8 (L2163-2174). Addendum §E10.3 MUST 1 (L418) matches byte-for-byte. `tenant_id=None` resolves to ambient `get_current_tenant_id()` per ml-tracking.md §10.2 (L1029-1031). Day-0 single-tenant newbie calling `await km.lineage(run_id)` gets a LineageGraph back, not a TypeError.

**F6 (MED-N2 from Round 5, ClearanceRequirement triple)** — This is the quiet hero of Phase-F. Prior version at addendum §E11.1 had `clearance_level: Optional[Literal["D","T","R","DTR"]]` which conflates axis (D / T / R per Decision 12 in `rules/pact-governance.md`) with level (L / M / H per §E9.2). A practitioner trying to encode "this method requires Medium data clearance AND Low transform clearance" had no way to express it under the flat Literal — "DTR" meant "applies on all three axes" but provided no level granularity. The new `ClearanceRequirement(axis, min_level)` tuple (L488-493) + `tuple[ClearanceRequirement, ...]` composition (L504) cleanly composes axis-specific levels. Worked example at L509-518 shows `(D:M, T:L)` binding. §E9.2 table at L314-328 already partitions methods by per-axis level — the dataclass shape now matches the table shape. This is the right partition.

---

## What's new / re-opened

### A11-NEW-2 — Engine-count drift between §E1.1 / §E11.3 MUST 4 / kaizen-ml §2.4.7 (NEW MED)

**Severity:** MEDIUM. Internal cross-reference inconsistency within a single file (+ 1 sibling). Not a contract drift like A11-NEW-1 (which was a cross-spec mandate with no consumer binding); this is a mechanical inconsistency that will fail Tier-2 test assertions at implementation time.

**Evidence (re-greped at audit):**

1. `addendum §E1.1` (L24-41, L43) — enumerates **18 engines** and asserts `18 engines; 18/18 auto-wire; 18/18 accept tenant_id; 18/18 accept actor_id`.
2. `addendum §E11.3 MUST 4` (L602) — "asserts `list_engines()` returns **all 13 engines** (MLEngine + 12 support engines) AND every `EngineInfo.signatures` tuple has **exactly 8 `MethodSignature` entries**".
3. `kaizen-ml §2.4.7` (L296) — "Assert the LLM-visible tool-spec list contains one entry per `MethodSignature` across **all 18 engines** listed in `ml-engines-v2-addendum §E1.1`".

Three numbers (18, 13, 18) cite the same underlying table. The "13 engines (MLEngine + 12 support engines)" claim at §E11.3 MUST 4 is stale — §E1.1 manually enumerates 18 rows (MLEngine + 17 support engines). Either §E1.1 needs to shrink to 13 OR §E11.3 MUST 4 needs to grow to 18.

Additionally, §E11.3 MUST 4 asserts "exactly 8 MethodSignature entries" per engine — this is the MLEngine eight-method surface (`setup`, `compare`, `fit`, `predict`, `finalize`, `evaluate`, `register`, `serve`) per §2.1 MUST 5. But §E1.1 shows support engines have different counts:

| Engine              | Methods listed in §E1.1                                               |
| ------------------- | --------------------------------------------------------------------- |
| `TrainingPipeline`  | `train` (1 method)                                                    |
| `ExperimentTracker` | `create_experiment`, `create_run`, `log_metric` (3)                   |
| `ModelRegistry`     | `register_model`, `promote_model`, `demote_model`, `delete_model` (4) |
| `FeatureStore`      | `register_group`, `materialize`, `ingest`, `erase_tenant` (4)         |
| `InferenceServer`   | `predict`, `predict_batch`, `predict_with_shadow` (3)                 |
| `DriftMonitor`      | `set_reference_data`, `check_drift`, `schedule_monitoring` (3)        |

None of these support engines has 8 public methods. The "exactly 8 MethodSignature entries per engine" assertion at §E11.3 MUST 4 would fail at the Tier-2 test against any of them.

**Practitioner lens.** This matters because the Tier-2 wiring test `test_engine_registry_signature_discovery.py` is a named merge-gate artifact. If the test is implemented literally to §E11.3 MUST 4's language, it will assert count=13 × signatures=8 per engine and fail on any support engine. A reviewer reading the addendum sees contradictory invariants and has to pick one — which is exactly the cross-spec-drift failure mode `rules/specs-authority.md §5b` exists to prevent (the full-sibling sweep didn't catch this because it's WITHIN one file + ONE sibling rather than ACROSS two specs).

**Recommended fix (~10 min):**

- `addendum §E11.3 MUST 4` — update "all 13 engines (MLEngine + 12 support engines)" → "all 18 engines (MLEngine + 17 support engines) per §E1.1"; update "exactly 8 MethodSignature entries" → "the number of MethodSignature entries matches each engine's §E1.1 public-method row (MLEngine has 8 per §2.1 MUST 5; support engines vary per their §E1.1 Key Methods column)".
- `kaizen-ml §2.4.7` — already says "all 18 engines" (correct); no change needed.

**Why MED, not HIGH.** The contradiction is visible at implementation time (the Tier-2 test will either be correctly authored OR fail on first run), not runtime. No production crash. No security hole. But a 1.0.0 release that ships with a Tier-2 merge-gate test whose spec is self-contradicting IS the institutional-knowledge bug that Round 6 senior-practitioner review exists to catch. A reviewer will have to pick which number is right and write commit-body justification, doubling the review cost. Fix the spec first.

### Carryovers from Round 4 (unchanged — third round restated)

- **v1.1 Strategic Primitives roadmap appendix** (MED) — `ml-engines-v2-draft.md §14` still does NOT bind the 6 Section-D OPEN primitives (Model Card, quantization/pruning/distillation, ensemble registry, `DatasetVersion` public surface, inference-time explainability, cost dashboard / `cost_usd` on `TrainingResult`, BYO-judge leaderboard, OIDC/SAML `actor_id` identity-provider binding) to the `kailash-ml/v1.1-strategic` milestone label. Third round flagged.
- **v1.1 Hardening roadmap appendix** (MED) — `ml-engines-v2-draft.md §14` still does NOT bind the 7 Section-B OPEN edge cases (warm-restart LR indexing, dataloader persistent_workers contextvar, read-replica RYW, drift schema mismatch, SDK-upgrade DL checkpoint migration, deleted-artifact leaderboard, spot-preemption heartbeat, WS multi-frame prompt accumulation) to `kailash-ml/v1.1-hardening`. Third round flagged.

Neither blocks CERTIFIED per Round-4 language, but the institutional ratchet is visible — if Round 7 lands without them filed, the spec authors are de facto shipping the roadmap commitments as prose-only promises. Practitioner recommendation unchanged: file before 1.0.0-rc.

---

## Production scenarios — walkthrough

Each scenario is what I'd actually script in my `Jupyter` or `ipython` session on day one. For each, I re-derive spec coverage from scratch.

### Scenario 1: "I need to register a model signed by a PACT-gated path and serve it via the REST channel while emitting to the ambient tracker"

Script:

```python
import kailash_ml as km
from kailash_pact import GovernanceEngine

with km.track("q4-churn-retrain", tenant_id="acme", actor_id="data-scientist-42"):
    engine = km.MLEngine()  # tenant_id + actor_id picked up from ambient
    engine.setup(df, target="churned")
    result = engine.fit(family="lightgbm")  # auto-emits to tracker run
    registered = engine.register(result, name="churn-v4")  # PACT check at register-time (E9.3 MUST 1)
    served = engine.serve(registered, channels=["rest"])  # PACT check: stage=staging → D:M, T:H, R:Human
    print(registered.artifact_uris)  # {"onnx": "cas://sha256:abc..."}
    print(registered.onnx_status)    # "clean" | "custom_ops" | "legacy_pickle_only"
```

**Does the spec support it?** YES, end-to-end.

- `km.track` ambient binding — `ml-tracking-draft.md §2`, accessor §10.2 L1029-1031.
- `km.MLEngine(tenant_id=None, actor_id=None)` picks up from ambient — `addendum §E3.1 MUST 1` L149-157.
- `engine.fit` auto-emits to tracker — `addendum §E1.2 MUST 1` L47-74 (18/18 engines).
- `engine.register` + PACT check — `addendum §E9.1` L312, `§E9.2` L320-321 (`MLEngine.register(stage="staging") = M, M, Agent`), `§E9.3 MUST 1` L331-333.
- `registered.artifact_uris` — `ml-registry-draft.md §7.1` L424 (F3 closure).
- `registered.onnx_status` — `ml-registry-draft.md §7.1` L429 (F3 closure) + §5.6.2 L234-244.
- `engine.serve(channels=["rest"])` + PACT check — `addendum §E9.2` L323 (D:M, T:H, R:Human), serving-side ONNX resolution at `ml-serving-draft.md §2.5.1` L214-216.

Every line number re-greped at audit. No gaps.

### Scenario 2: "A Kaizen agent wants to discover ML tools and their clearance requirements"

Script:

```python
import kailash_ml as km
from kailash_ml.engines.registry import EngineInfo, MethodSignature, ClearanceRequirement
from kaizen.agents import MLAwareAgent

# Agent construction — discovery at init time
agent = MLAwareAgent(tenant_id="acme")
tools = agent._build_ml_tools()  # derived from km.list_engines()

# Senior DS inspects one engine's contract
training_info: EngineInfo = km.engine_info("TrainingPipeline")
print(training_info.version)              # "1.0.0" — equals kailash_ml.__version__
print(training_info.accepts_tenant_id)    # True
print(training_info.emits_to_tracker)     # True
print(training_info.clearance_level)      # (ClearanceRequirement(axis="D", min_level="M"),
                                          #  ClearanceRequirement(axis="T", min_level="L"))
print(training_info.extras_required)      # ()  — or ("dl",) for DL-family engines

# Check if agent is allowed to call register(stage="production")
for sig in training_info.signatures:
    if sig.method_name == "train" and sig.is_deprecated:
        continue  # skip deprecated per §2.4.3
    # Build tool descriptor
    ...
```

**Does the spec support it?** YES — F4 closed A11-NEW-1 and F6 made `clearance_level` composable.

- `km.list_engines()` / `km.engine_info(name)` — `addendum §E11.2` L562-582.
- `EngineInfo` shape — `addendum §E11.1` L494-506.
- `ClearanceRequirement(axis, min_level)` + `tuple[ClearanceRequirement, ...]` composition — `addendum §E11.1` L488-516.
- Version-sync invariant — `addendum §E11.3 MUST 3` L594-596 (binding to zero-tolerance Rule 5).
- Tenant-scoped filtering in agent init — `kaizen-ml §2.4.3` L172-195.
- `is_deprecated` skip — `MethodSignature.is_deprecated` at `addendum §E11.1` L477, binding at `kaizen-ml §2.4` (implicit — §2.4.3's `_is_clearance_admissible` filter is the pattern).

**Practitioner quality of EngineInfo surface (specific probe):**

- ✅ `accepts_tenant_id` — immediately tells me whether I need to wrap the call in a tenant context.
- ✅ `emits_to_tracker` — immediately tells me whether I need to instrument for observability.
- ✅ `clearance_level` as `tuple[ClearanceRequirement, ...]` — composable, axis-specific. I can write `if ClearanceRequirement("R", "Human") in info.clearance_level: require_human_approval()`.
- ✅ `is_deprecated` + `deprecated_since` + `deprecated_removal` — deprecation tracking absent from MLflow/W&B/Neptune/Comet. Senior-grade.
- ✅ `extras_required` — tells me if `pip install kailash-ml[dl]` is needed before calling this engine.
- ⚠️ Minor: `version` is a `str` semver, not a structured dataclass. That's fine — `packaging.version.parse()` is one hop away.
- ⚠️ A11-NEW-2 applies here: if the Tier-2 test at §E11.3 MUST 4 was implemented literally, it would fail on support engines. A senior Kaizen engineer reading §E11.3 MUST 4 and §E1.1 side-by-side will escalate within 5 minutes.

Overall: EngineInfo exposes what a Kaizen agent needs. Gap closed.

### Scenario 3: "Team lead wants the lineage graph from a production run_id to trace a model back to its training dataset and upstream features"

Script:

```python
import kailash_ml as km

# Production run_id from PagerDuty alert
run_id = "prod-run-20260421-0847"
with km.track(tenant_id="acme"):  # ambient tenant via contextvar
    graph = await km.lineage(run_id)  # max_depth=10, tenant_id resolved from ambient

print(graph.root_id)                     # the run_id
for node in graph.nodes:
    print(node.kind, node.id, node.label)  # "run" | "dataset" | "feature_version" | "model_version" | "deployment"
for edge in graph.edges:
    print(edge.source_id, edge.relation, edge.target_id)

# Filter to the dataset that produced the run
datasets = [n for n in graph.nodes if n.kind == "dataset"]
assert len(datasets) == 1  # a single training pass has one dataset
print(datasets[0].metadata.get("dataset_hash"))  # "sha256:..."
print(datasets[0].tenant_id)                     # "acme" — every node tenant-scoped
```

**Does the spec support it?** YES — F5 closed the signature gap.

- `km.lineage(run_id_or_model_version_or_dataset_hash, *, tenant_id: str | None = None, max_depth: int = 10)` — `ml-engines-v2-draft.md §15.8` L2163-2174 (F5 closure) + `addendum §E10.3 MUST 1` L418.
- `tenant_id=None` ambient resolution — `ml-tracking-draft.md §10.2` L1029-1031.
- `LineageGraph` dataclass — `addendum §E10.2` L399-412.
- `LineageNode.tenant_id` required (never None) — `addendum §E10.2` L380.
- Cross-tenant raises `CrossTenantReadError` — `addendum §E10.3 MUST 2` L428-430.

**Practitioner quality of the §E13.1 workflow (specific probe):**

The §E13.1 mandatory E2E test at `addendum` L633-650 is a 13-step flow:

1. Enter `km.track("e2e-lifecycle")` context.
2. Construct `km.MLEngine(tenant_id="test-acme", actor_id="ci-runner")`.
3. `engine.setup(df, target="label")`.
4. `engine.fit(family="lightgbm")`.
5. `engine.diagnose(result)`.
6. `engine.register(result)`.
7. `engine.serve(registered, channels=["rest"])`.
8. POST /predict and read a response.
9. `engine.monitor(registered, interval_hours=24)`.
10. Assert 18 engines emitted to shared tracker DB.
11. Assert every row carries `tenant_id="test-acme"` (multi-tenant verified end-to-end).
12. Assert `km.lineage(registered.model_uri, tenant_id=engine.tenant_id)` contains the expected nodes.
13. Assert Prometheus `/metrics` has `ml_inference_total{model="...",outcome="success"}` ≥ 1.

**Does this match what a senior engineer would script?** YES — I would write exactly this test (and have, at two prior companies). Step 12's note that `km.lineage` is the canonical top-level wrapper (engine has NO `.lineage()` method per the eight-method surface) prevents a reviewer from asking "why isn't this on the engine?" — the spec preempts the question at L648.

Two minor observations for a senior lens:

- Step 10 asserts "18 engines emitted" — this is the correct number per §E1.1 and resolves the A11-NEW-2 ambiguity in favor of 18 (so the fix should update §E11.3 MUST 4 to match, not §E13.1 or §E1.1).
- Step 8 says "POST /predict" — a senior would also want to check the response contract (shape/status). Implicit in `ml-serving §2.5` but could be tightened. Not a blocker.

### Scenario 4: "Senior DS wants to inspect EngineInfo for a custom engine they are adding"

Script:

```python
# I'm adding a new engine; I want to verify it registers correctly and is agent-discoverable
from kailash_ml.engines.registry import register_engine, EngineInfo, ClearanceRequirement
from kailash_ml import __version__

@register_engine  # decorator populates the registry at import-time (E11.3 MUST 2)
class CausalInferenceEngine:
    """ATT / ATE estimation via doubly-robust learners."""

    __engine_info__ = EngineInfo(
        name="CausalInferenceEngine",
        version=__version__,  # MUST equal kailash_ml.__version__ atomically (E11.3 MUST 3)
        module_path="kailash_ml.engines.causal",
        accepts_tenant_id=True,
        emits_to_tracker=True,
        clearance_level=(
            ClearanceRequirement(axis="D", min_level="M"),  # reads sensitive outcome data
            ClearanceRequirement(axis="T", min_level="H"),  # transforms it into causal estimates
        ),
        signatures=(...),
        extras_required=("causal",),  # pip install kailash-ml[causal]
    )
    ...

# Verify discovery from my REPL
import kailash_ml as km
info = km.engine_info("CausalInferenceEngine")
assert info.version == km.__version__
```

**Does the spec support it?** YES.

- `@register_engine` decorator — `addendum §E11.3 MUST 2` L590-592 ("populated at import-time by decorator. An engine without an `EngineInfo` entry is not discoverable").
- `EngineInfo` fields — `addendum §E11.1` L494-506.
- `ClearanceRequirement(axis, min_level)` composition — `addendum §E11.1` L488-516 (F6 closure).
- `extras_required=("causal",)` — `addendum §E11.1` L506 (Decision 13 hyphen convention). Agent discovery sees the extras-required and can prompt `pip install kailash-ml[causal]` before invoking.
- Version-sync binds `__version__` — `addendum §E11.3 MUST 3` L594-596.

The `@dataclass(frozen=True)` + `__engine_info__` pattern is ergonomic. I'd add one more thing as a senior — a registry linter that fails at import-time if `__engine_info__.name` doesn't match the class name (catches copy-paste errors) — but that's implementation, not spec.

One genuine gap: the spec does NOT explicitly specify whether `register_engine` is an opt-in decorator OR applied automatically by a metaclass. §E11.3 MUST 2 says "populated at import-time by decorator" — reads as opt-in. But §E1.1 enumerates 18 engines and MUST 2 says "An engine without an `EngineInfo` entry is not discoverable — and therefore not available to agents — so forgetting the decorator is a loud failure, not a silent one". A senior reviewer would want one more line: "Every engine class in `kailash_ml/engines/*.py` MUST carry the `@register_engine` decorator; the CI linter `test_all_engines_registered.py` grep-asserts this at merge gate." Not blocking CERTIFIED but worth noting in Round 7 synthesis.

---

## Final verdict rationale

**CERTIFIED.** Four specific reasons, in order of load-bearing weight:

1. **Phase-F closed every HIGH / new-MED from Round 5 at the spec level.** A11-NEW-1 gets a full §2.4 in kaizen-ml-integration (not a single paragraph — 8 subsections, worked example, BLOCKED pattern, Tier-2 wiring test). HIGH-R5-1 (RegisterResult field shape) gets both the canonical `artifact_uris: dict[str, str]` AND a deprecation shim for v1.x legacy. L-1 (km.lineage signature) gets ambient-resolved `tenant_id: str | None = None` matching every sibling km.\* verb. N2 (ClearanceRequirement flat→triple) gets a cleanly-composed axis/level separation. Round 5's "CERTIFIED + 1 NEW MED" becomes Round 6's "CERTIFIED + 1 different new MED (A11-NEW-2, a self-contained file-internal fix)".

2. **The practitioner-facing surfaces all pass the "would I script this Monday morning" test.** Scenarios 1-4 above are what I'd actually type into `ipython` on my first day at a kailash-ml adopter. Each completes with zero spec-level blockers. `artifact_uris["onnx"]` is what I reach for. `ClearanceRequirement(axis="D", min_level="M")` is what I encode for per-method PACT rules. `km.lineage(run_id)` is what I type at 3am on page. `@register_engine` is what I decorate my new engine with. Every one works.

3. **Senior-grade features that competitors lack.** `MethodSignature.is_deprecated` / `deprecated_since` / `deprecated_removal` — MLflow, W&B, Neptune, Comet, ClearML all lack programmatic deprecation tracking. `EngineInfo.accepts_tenant_id` / `emits_to_tracker` / `clearance_level` / `extras_required` — programmatic introspection of operational contracts, again absent elsewhere. `RegisterResult.onnx_status` as a 3-value `Literal` ontology — the partition ("clean" / "custom_ops" / "legacy_pickle_only") is the correct partition; vendors who collapse to a single boolean bite themselves on ort-extensions deployment steps. The Quick Start SHA-pin (Round 5 verified at 246 bytes / 6 lines) is the correct structural defense against documentation drift. These are not surface features — they're the quiet-hero features that a senior DS evaluating "do I adopt this for my team" checks for.

4. **The failure mode that matters at 1.0.0 is institutional-knowledge drift, not capability gaps.** A11-NEW-2 (engine-count 13 vs 18, method-count "exactly 8" vs variable) is exactly that failure mode — two internal claims in one file that don't agree, caught by mechanical counting in my re-greping, fix-able in 10 minutes. Round 4's A10-3, Round 5's A11-NEW-1, Round 6's A11-NEW-2 are all the same failure mode at decreasing severity (HIGH cross-spec → MED cross-spec sibling → MED within-file). The severity is decreasing, not increasing — the specs are converging. This is the signal to ship.

**What convinces me:** the Phase-F edits are surgical and they integrate. The deprecation shim at §7.1.1 is legitimate senior-grade engineering (NOT a shim that subclasses the canonical dataclass — a `@property` on the same class, `DeprecationWarning` on access, field-level `str` would be a pickle-drift hazard explicitly avoided). The ClearanceRequirement dataclass separation addresses a real composition gap. The kaizen-ml §2.4 re-imports rather than redefines. These are the choices a team that has shipped an ML platform before makes.

**Would I stake my team on kailash-ml 1.0.0 as specced NOW?** YES, conditional on (a) A11-NEW-2's 10-minute fix before 1.0.0-rc tag, AND (b) the two Round-4 roadmap-binding commits (v1.1-strategic + v1.1-hardening labels). These together are ~30 minutes of spec work + 2 gh-label filings. The spine is production-ready.

---

## Drafts audited (re-greped at audit time)

- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-engines-v2-draft.md` (2473 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-engines-v2-addendum-draft.md` (~700 lines — grew from 670 after Phase-F F6)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-registry-draft.md` (1067 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-serving-draft.md` (1214 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-tracking-draft.md` (1266 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-dashboard-draft.md` (810 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-feature-store-draft.md` (732 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-drift-draft.md` (885 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-diagnostics-draft.md` (1070 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/supporting-specs-draft/kaizen-ml-integration-draft.md` (~600 lines — grew from 430 after Phase-F F4's §2.4 addition)

Every line number cited above was re-greped at audit time per `rules/testing.md` audit-mode re-derivation protocol. Prior-round line numbers not trusted; Phase-F edits shifted numbering throughout.

---

## Findings file (absolute path)

`/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-6-senior-practitioner.md`
