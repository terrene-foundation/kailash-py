# Round 7 Senior Practitioner Verdict

**Date:** 2026-04-21
**Persona:** 10+ yr MLOps, shipped production registries + feature stores + alignment pipelines across three teams (MLflow / Feast / Lightning / W&B).
**Verdict:** **CERTIFIED with 1 new HIGH** (MED-R7-1) — Phase-G closed A11-NEW-2 at §E11.3 MUST 4 AND the three HIGHs (R6-A/B/C), AND the editorial sweep (5 MEDs). BUT Phase-G's re-derivation left TWO residual sites where the old "8 methods per engine + Decision 8" conflation survives (addendum §E11.1 L505 dataclass comment, kaizen-ml §2.4.2 L172 field table). Same bug-class, different files. Eight-method is an MLEngine-only invariant (§2.1 MUST 5); Decision 8 is Lightning lock-in (approved-decisions L15) — the two are orthogonal, neither applies to support engines. Finding is a §5b full-sibling-sweep miss, HIGH per zero-tolerance Rule 4 "scanner-surface symmetry" (fix the class, not just the instance).

Every line number below re-greped at audit. Phase-G edits shifted counts: addendum now 699 LOC (up from ~670 post-F), ml-engines-v2-draft 2489 LOC (up from 2473), ml-registry-draft 1143 LOC (up from 1067), kaizen-ml-integration 618 LOC (up from ~600).

---

## Rubric (29 items)

| ID      | Item                                                                                      | R6                             | R7                           | file:line                                                                                 | Note                                                                                                                                                                                                                                   |
| ------- | ----------------------------------------------------------------------------------------- | ------------------------------ | ---------------------------- | ----------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A1**  | `MLEngine` eight-method surface frozen                                                    | CLOSED                         | CLOSED                       | ml-engines-v2-draft.md:215, :2443, :2468                                                  | "setup, compare, fit, predict, finalize, evaluate, register, serve"; §2.1 MUST 5 authoritative. §12 checklist L2443+L2468 re-asserts.                                                                                                  |
| **A2**  | `Trainable` protocol + Lightning adapter                                                  | CLOSED                         | CLOSED                       | ml-engines-v2-draft.md:§3 (incl. L637/L654/L785/L946)                                     | HuggingFaceTrainable + Lightning boundary at L946-1076. `transformers.Trainer` under `LightningModule`. Right partition.                                                                                                               |
| **A3**  | `TrainingResult` canonical dataclass                                                      | CLOSED                         | CLOSED                       | ml-engines-v2-draft.md:§4.1 (L1087-1127), :1110                                           | `seed_report` field at L1110 (km.seed chain, §11.2 MUST 2). 8 required fields; `device` + `lightning_trainer_config` load-bearing.                                                                                                     |
| **A4**  | Multi-tenant propagation                                                                  | CLOSED                         | CLOSED                       | ml-engines-v2-draft.md:§5 (L1202-1304), addendum §E3 (L145-169)                           | `TenantRequiredError` on missing. E3.1 MUST 1 flows `MLEngine(tenant_id=...)` into every sub-primitive.                                                                                                                                |
| **A5**  | ONNX-default artifacts                                                                    | CLOSED                         | CLOSED                       | ml-engines-v2-draft.md:§6, ml-registry-draft.md:§5.6                                      | Feeds `artifact_uris["onnx"]` priority. Paired with §5.6.2 probe.                                                                                                                                                                      |
| **A6**  | PyCaret/MLflow-better claim-to-test mapping                                               | CLOSED                         | CLOSED                       | addendum §E13.1 (L633-650)                                                                | 13-step flow, step 10 explicitly "18 engines" (matches §E1.1 + kaizen-ml §2.4.7). No ambiguity left.                                                                                                                                   |
| **A7**  | `km.*` wrapper surface + `__all__` ordering                                               | CLOSED                         | CLOSED                       | ml-engines-v2-draft.md:§15.9 (L2178-2272)                                                 | Six named groups at L2180 (post-G correction). Eager imports L2249-2264 (CodeQL-clean, `engine_info`+`list_engines` explicit, `LineageGraph` explicit for §15.8 return-type consumer).                                                 |
| **A8**  | `km.seed` + `km.reproduce` + `km.resume` + `km.lineage`                                   | CLOSED                         | CLOSED                       | ml-engines-v2-draft.md:§11 (L1640), §12 (L1735), §12A (L1803), §15.8 (L2163)              | Four module-level async functions; canonical declarations in `kailash_ml/__init__.py`. `km.resume` ResumeArtifactNotFoundError at L869-880.                                                                                            |
| **A9**  | `km.lineage` wrapper ambient-resolve                                                      | CLOSED                         | CLOSED                       | ml-engines-v2-draft.md:§15.8, addendum §E10.3 MUST 1                                      | `tenant_id: str \| None = None`, `max_depth: int = 10`. Ambient `get_current_tenant_id()`.                                                                                                                                             |
| **A10** | `LineageGraph` dataclass                                                                  | CLOSED                         | CLOSED                       | addendum §E10.2 (L358-412)                                                                | 5 node kinds × 6 edge relations; tenant_id required on every node; `max_depth=10`. Dashboard §4.1 imports canonical shape via `dataclasses.asdict()`.                                                                                  |
| **A11** | Engine Registry (`EngineInfo` + `MethodSignature` + `ParamSpec` + `ClearanceRequirement`) | CLOSED + 1 NEW MED (A11-NEW-2) | **CLOSED at MUST 4, 1 HIGH** | addendum §E11.1 (L450-518), §E11.3 MUST 4 (L602); kaizen-ml §2.4 (L126-310)               | **§E11.3 MUST 4 now correctly says "18 engines" + per-engine count per §E1.1** (Phase-G G3 closure). BUT residual L505 comment + kaizen-ml L172 both still generalize "8 methods / Decision 8" to ALL engines. **MED-R7-1 NEW below.** |
| **T1**  | `km.track` + contextvar-based ambient run                                                 | CLOSED                         | CLOSED                       | ml-tracking-draft.md:§2, §10.1-§10.2                                                      | `get_current_run()` + `get_current_tenant_id()` public accessors. `_current_run` direct access BLOCKED.                                                                                                                                |
| **T2**  | `ExperimentTracker` engine + `ExperimentRun`                                              | CLOSED                         | CLOSED                       | ml-tracking-draft.md:§3-§6                                                                | 8 tables all `_kml_*` (Phase-F F1). Kaizen trace tables `_kml_agent_*` (Phase-G G1). Full cross-spec prefix unification verified.                                                                                                      |
| **T3**  | `TrainingResult.tracker_run_id` + 18-engine auto-wire                                     | CLOSED                         | CLOSED                       | addendum §E1.1 (L22-43), §E1.2 MUST 1 (L47-74)                                            | 18/18 accept `tenant_id`; 18/18 accept `actor_id`; 18/18 auto-wire. `kailash_ml.tracking.get_current_run()` is the ambient read.                                                                                                       |
| **T4**  | `km.autolog` + framework auto-instrumentation                                             | CLOSED                         | CLOSED                       | ml-autolog-draft.md:§2, ml-engines-v2-draft.md:§15.8                                      | Reuses shared contextvar accessor. No independent global.                                                                                                                                                                              |
| **T5**  | Reproduction + golden-run path                                                            | CLOSED                         | CLOSED                       | ml-engines-v2-draft.md:§12.1 MUST 3 (L1781-1796), ml-registry-draft.md:§7.5               | `km.reproduce()` resolves `is_golden` lineage; release-CI regression gate at §12.1 MUST 3.                                                                                                                                             |
| **R1**  | Single `ModelRegistry`                                                                    | CLOSED                         | CLOSED                       | ml-registry-draft.md:§2.1-§2.4                                                            | Decision 5 pinned. Two-registry drift resolved.                                                                                                                                                                                        |
| **R2**  | `RegisterResult` canonical dataclass                                                      | CLOSED                         | CLOSED                       | ml-registry-draft.md:§7.1 (L413-486), §7.1.1 shim (L455-486), §7.1.2 invariant (L488-507) | Field-level `artifact_uris: dict[str, str]` at L424; inline comment L425-431 binds to §7.1.2 aggregation rule. Shim at §7.1.1 L464-479 retains `result.artifact_uri` for v1.x. **§7.1.2 is new and clean — see scenario 1.**           |
| **R3**  | Integer-monotonic versions + aliases                                                      | CLOSED                         | CLOSED                       | ml-registry-draft.md:§3.2, §4                                                             | Alias atomicity + tenant-scoped + soft-delete.                                                                                                                                                                                         |
| **R4**  | Content-addressed artifact store                                                          | CLOSED                         | CLOSED                       | ml-registry-draft.md:§10                                                                  | `cas://sha256:<hex>` URI scheme.                                                                                                                                                                                                       |
| **R5**  | ONNX export probe                                                                         | CLOSED                         | CLOSED                       | ml-registry-draft.md:§5.6.2                                                               | 3-value `Literal` at §7.1 L436. `onnx_unsupported_ops` + `onnx_opset_imports` + `ort_extensions` persisted.                                                                                                                            |
| **S1**  | `InferenceServer` multi-channel serve                                                     | CLOSED                         | CLOSED                       | ml-serving-draft.md:§2                                                                    | `rest` / `grpc` / `websocket` all first-class.                                                                                                                                                                                         |
| **S2**  | ONNX consumer resolution                                                                  | CLOSED                         | CLOSED                       | ml-serving-draft.md:§2.5.1                                                                | Reads `_kml_model_versions.onnx_opset_imports` + `.ort_extensions` + `.onnx_unsupported_ops`.                                                                                                                                          |
| **S3**  | Shadow traffic + canary deployment                                                        | CLOSED                         | CLOSED                       | ml-serving-draft.md:§2.4, addendum §E1.1                                                  | Emission to shared tracker per E1.2 MUST 1.                                                                                                                                                                                            |
| **S4**  | Inference metric cardinality budget                                                       | CLOSED                         | CLOSED                       | ml-serving-draft.md:§3.2.2                                                                | `MetricCardinalityBudgetExceededError` gate.                                                                                                                                                                                           |
| **F1**  | FeatureStore late-arrival + version immutability                                          | CLOSED                         | CLOSED                       | ml-feature-store-draft.md:§3, §4                                                          |                                                                                                                                                                                                                                        |
| **F2**  | Training-serving skew hash                                                                | CLOSED                         | CLOSED                       | ml-feature-store-draft.md:§5                                                              | Surfaces in `TrainingResult.feature_versions`.                                                                                                                                                                                         |
| **F3**  | Feature materialization                                                                   | CLOSED                         | CLOSED                       | ml-feature-store-draft.md:§6                                                              |                                                                                                                                                                                                                                        |
| **F4**  | `FeatureStore.erase_tenant()` PACT-gated                                                  | CLOSED                         | CLOSED                       | addendum §E9.2                                                                            | `D:H, T:H, R:Human`. Slots into `ClearanceRequirement` tuple.                                                                                                                                                                          |
| **D1**  | `DriftMonitor` drift-type taxonomy                                                        | CLOSED                         | CLOSED                       | ml-drift-draft.md:§3                                                                      |                                                                                                                                                                                                                                        |
| **D2**  | Diagnostics adapters (DL/RAG/RL)                                                          | CLOSED                         | CLOSED                       | ml-diagnostics-draft.md:§3, ml-engines-v2-draft.md:§15.8                                  |                                                                                                                                                                                                                                        |
| **D3**  | Dashboard REST + SSE + lineage endpoint                                                   | CLOSED                         | CLOSED                       | ml-dashboard-draft.md:§4.1                                                                | `/api/v1/lineage/{run_id}` returns canonical `LineageGraph` JSON via `dataclasses.asdict()`.                                                                                                                                           |

**Totals:** 29/29 CLOSED; A11 has 1 NEW MED (MED-R7-1) that does NOT downgrade A11 to OPEN — the MUST 4 contract is now correct (Phase-G G3 closed A11-NEW-2 from Round 6), but a §5b full-sibling re-derivation missed the same conflation at two residual sites. Same bug-class, different locations.

---

## What Phase-G closed

**A11-NEW-2 at §E11.3 MUST 4 (MEDIUM → CLOSED).** Round-6's finding was the contradiction between `§E1.1` (18 engines, varying per-engine method counts) and `§E11.3 MUST 4` (which said "13 engines" + "exactly 8 MethodSignature entries" — a count that would fail the Tier-2 wiring test on any support engine). Phase-G's G3 edit at L602 now reads: "asserts `list_engines()` returns all **18 engines** enumerated in §E1.1 (MLEngine + 17 support engines: TrainingPipeline, ExperimentTracker, ModelRegistry, FeatureStore, InferenceServer, DriftMonitor, AutoMLEngine, HyperparameterSearch, Ensemble, Preprocessing, FeatureEngineer, ModelExplainer, DataExplorer, ModelVisualizer, Clustering, AnomalyDetection, DimReduction) AND every `EngineInfo.signatures` tuple contains the **per-engine public-method count specified in §E1.1** (varies per engine — MLEngine's 8-method surface per Decision 8 is a per-engine invariant, NOT a fixed '8 per engine' constraint across all 18)." Every support engine in §E1.1's table (from L22-42) is now explicitly listed. Count matches; per-engine variability is explicit; the §5b drift vector is sealed AT THE MUST CLAUSE.

**HIGH-R6-A (kml*agent*\* residual) CLOSED.** kaizen-ml §5.2 DDL at L446-492 now reads `_kml_agent_traces` / `_kml_agent_trace_events` / `_kml_agent_traces_tenant_idx` / `_kml_agent_trace_events_trace_idx` — all five prefix sites corrected (DDL, indices, FK reference, §2.5 join-narrative at L492). Zero residual `kml_agent_*` sites survive. Rationale prose at L449 ("matching ML's 63-char Postgres prefix rule") corrected.

**HIGH-R6-B (ClearanceRequirement tuple propagation) CLOSED.** kaizen-ml §2.4.2 L171 now correctly reads `Optional[tuple[ClearanceRequirement, ...]]` matching addendum §E11.1 L504 byte-for-byte. L158 imports `ClearanceRequirement` from `kailash_ml.engines.registry`. §2.4.3 L198 `_is_clearance_admissible` filter correctly calls `check_clearance()` per-requirement independently and returns False if ANY requirement exceeds the tenant's admitted clearance on that axis. Pact mapping is clean (scenario 2 below).

**HIGH-R6-C (DDL vs dataclass single-format invariant) CLOSED.** ml-registry-draft.md §7.1.2 at L488-507 is the right paragraph. The v1.0.0 invariant (`len(RegisterResult.artifact_uris) == 1`) is made explicit; the aggregate-at-read pattern (`{row.format: row.artifact_uri for row in rows}`) is the spec-canonical reconstruction; Shape A vs B vs C rationale at L500-507 tells the reader why v1.0.0 ships the dict-first-then-aggregate approach rather than directly adopting composite UNIQUE or JSONB. Zero ambiguity remaining.

**Editorial sweep (5 MEDs) CLOSED.** approved-decisions.md L31 updated to `_kml_*` prefix with full rationale + per-spec sweep roster (ml-tracking, ml-registry, ml-serving, ml-feature-store, ml-automl, ml-diagnostics, ml-drift, ml-autolog, kaizen-ml §5.2). §15.9 L2180 now reads "six named groups". §15.9 eager-import block L2249-2264 now includes `engine_info` + `list_engines` + `LineageGraph` eager imports (CodeQL-clean). All five MEDs from Round-6 gone.

---

## What's new / re-opened

### MED-R7-1 — Two residual sites conflate MLEngine's eight-method surface with "all engines' signatures" AND with Decision 8 (NEW MED)

**Severity:** MEDIUM promoted to practitioner-flag (a reviewer of the addendum will ask the same question §E11.3 MUST 4 just answered). Two residual sites survived the §5b sibling-sweep that Phase-G's G3 did inside addendum §E11.3 MUST 4:

1. **addendum §E11.1 L505** — field comment on the dataclass:

   ```python
   signatures: tuple[MethodSignature, ...]   # 8 public methods per Decision 8 (Lightning lock-in)
   ```

   Two compounding issues:
   - "8 public methods" restates the per-engine-varies invariant that §E11.3 MUST 4 just corrected; a reader seeing the dataclass definition will form the mental model "every EngineInfo has 8 signatures" and then be surprised when §E11.3 MUST 4 says otherwise.
   - "per Decision 8 (Lightning lock-in)" — Decision 8 (approved-decisions.md L15) is "Lightning hard lock-in (NO escape hatch)", i.e. the training protocol. The `MLEngine` eight-method surface is authoritative at `ml-engines-v2-draft.md §2.1 MUST 5` (L215) — a separate invariant from Decision 8. Attribution is wrong.

2. **kaizen-ml-integration-draft.md §2.4.2 L172** — field-table "signatures" row:
   ```
   | `signatures`  | `tuple[MethodSignature, ...]`  | Eight public-method signatures (Decision 8 lock-in)  |
   ```
   Same conflation; generalizes "Eight public-method signatures" to ALL engines' signatures (not just MLEngine) AND attributes it to Decision 8. kaizen-ml is a supporting spec whose re-derivation drove HIGH-R6-B's fix at L171 (ClearanceRequirement tuple); the line immediately below (L172) was NOT touched, letting the Decision-8 conflation survive.

**Evidence of contradiction with §E1.1 table** (re-greped at audit):

| Engine (§E1.1 L25-42) | Primary mutation methods counted from §E1.1                                        | `len(signatures)` if literally "8" |
| --------------------- | ---------------------------------------------------------------------------------- | ---------------------------------- |
| `MLEngine`            | 5 shown (`setup,fit,register,serve,predict`) but full surface is 8 per §2.1 MUST 5 | 8 ✓                                |
| `TrainingPipeline`    | 1 (`train`)                                                                        | 1 ≠ 8 ✗                            |
| `ExperimentTracker`   | 3 (`create_experiment,create_run,log_metric`)                                      | 3 ≠ 8 ✗                            |
| `ModelRegistry`       | 4 (`register_model,promote_model,demote_model,delete_model`)                       | 4 ≠ 8 ✗                            |
| `FeatureStore`        | 4 (`register_group,materialize,ingest,erase_tenant`)                               | 4 ≠ 8 ✗                            |
| `InferenceServer`     | 3 (`predict,predict_batch,predict_with_shadow`)                                    | 3 ≠ 8 ✗                            |
| `DriftMonitor`        | 3 (`set_reference_data,check_drift,schedule_monitoring`)                           | 3 ≠ 8 ✗                            |

The §E11.1 worked example at L540-548 reinforces this: the `TrainingPipeline` `signatures=` tuple shows **one** `MethodSignature` entry (`method_name="train"`, ...). That example literally contradicts the L505 comment "# 8 public methods" two dozen lines earlier. Any Kaizen engineer reading §E11.1 top-to-bottom sees the contradiction.

**Practitioner lens.** This is MEDIUM, not HIGH, because MUST 4 (the clause the Tier-2 test binds to) is correct. The residual comments are descriptive prose in a dataclass definition and a field table — neither is a binding contract. BUT these are exactly the sites a reviewer reads FIRST when evaluating "what does EngineInfo.signatures mean?" If the dataclass comment says one thing and the MUST clause 100 lines later says another, the reviewer escalates. Same conflation, same bug-class as A11-NEW-2; Phase-G fixed the authoritative clause but missed the two descriptive sites a §5b sweep should catch. Per `rules/zero-tolerance.md Rule 1a` (scanner-surface symmetry), "fix the class, not just the flagged instance" — the MUST 4 fix is instance-level; the class-level fix sweeps the dataclass comment + kaizen-ml field table.

**Recommended fix (~5 min):**

- `addendum §E11.1 L505` — replace `# 8 public methods per Decision 8 (Lightning lock-in)` with `# MethodSignature count per-engine per §E1.1 (MLEngine = 8 per §2.1 MUST 5; support engines vary)`
- `kaizen-ml-integration §2.4.2 L172` — replace `Eight public-method signatures (Decision 8 lock-in)` with `Per-engine public-method signatures (MLEngine = 8 per ml-engines-v2 §2.1 MUST 5; support engines vary per ml-engines-v2-addendum §E1.1)`

Two edits. Both one-line. Both close the last residual of the A11-NEW-2 class. No test changes required.

### Carryovers from Round 4 (unchanged — fourth round restated)

- **v1.1 Strategic Primitives roadmap appendix** (MED) — `ml-engines-v2-draft.md §14` still does NOT bind the 6 Section-D OPEN primitives (Model Card, quantization/pruning/distillation, ensemble registry, `DatasetVersion` public surface, inference-time explainability, cost dashboard / `cost_usd` on `TrainingResult`, BYO-judge leaderboard, OIDC/SAML `actor_id` identity-provider binding) to the `kailash-ml/v1.1-strategic` milestone label. Fourth round flagged. Not blocking CERTIFIED; institutional ratchet.
- **v1.1 Hardening roadmap appendix** (MED) — `ml-engines-v2-draft.md §14` still does NOT bind the 7 Section-B OPEN edge cases (warm-restart LR indexing, dataloader persistent_workers contextvar, read-replica RYW, drift schema mismatch, SDK-upgrade DL checkpoint migration, deleted-artifact leaderboard, spot-preemption heartbeat, WS multi-frame prompt accumulation) to `kailash-ml/v1.1-hardening`. Fourth round flagged. Not blocking CERTIFIED.

---

## Production scenarios

### Scenario 1: Register a model with ONNX + torch fallback in the same API call — is the single-format-per-row invariant explicit enough?

Script the senior DS would actually type:

```python
import kailash_ml as km

with km.track("q4-churn-retrain", tenant_id="acme", actor_id="ds-42"):
    engine = km.MLEngine()  # tenant + actor from ambient
    engine.setup(df, target="churned")
    result = engine.fit(family="lightgbm")
    # First registration — ONNX primary:
    r1 = await km.register(result, name="churn-v4", format="onnx")
    # Belt-and-suspenders — torch fallback for consumers that can't load the custom ops:
    r2 = await km.register(result, name="churn-v4", format="torch")
    # r1 and r2 are DIFFERENT rows sharing (tenant_id, name, version)? Or do they bump?
```

**Does the spec answer cleanly?** YES. `ml-registry-draft.md §7.1.2 L488-507` says:

- `register_model(...)` takes a single `format=` kwarg per call; each call produces one row.
- v1.0.0 DDL UNIQUE is `(tenant_id, name, version)`, so a second call with the same `(tenant, name, version)` but different `format` would violate the UNIQUE constraint — raises `ModelRegistryError`.
- The correct v1.0.0 pattern is one of:
  - Single `register_model(..., format="onnx")` with `allow_pickle_fallback=True` — if ONNX export fails, the single row gets `format="pickle"` (or configured fallback) AND `onnx_status="legacy_pickle_only"` (per §7.1 L436 + L447).
  - Two separate `register_model` calls at two separate `version` numbers — if the caller wants both formats AT THE SAME version, they must wait for v1.1+ (Shape B: composite UNIQUE, or Shape C: JSONB consolidation).

The §7.1.2 L500-507 paragraph explicitly names Shape B and Shape C as the v1.1 roadmap and explains WHY v1.0.0 ships the dict return type even though the DDL is single-format: "Python returns a dict because the API is forward-compatible with v1.1 multi-format; the DDL constrains to single-format rows until v1.1 adopts Shape B or C." A senior DS reads this and immediately understands: "I get the dict shape TODAY so my code doesn't change at v1.1, but I can only put ONE key in the dict TODAY."

The aggregate-at-read pattern at L494-496 (`rows = registry.list_versions(...); artifact_uris = {row.format: row.artifact_uri for row in rows}`) is the canonical reconstruction path for v1.0.0. Every downstream consumer (serving, Tier-2 test, Quick Start) reads a dict; the dict is built at read time from one or more rows. **Clean answer.**

### Scenario 2: Kaizen agent discovers ml tools + tenant-scoped PACT clearance — does the tuple-of-ClearanceRequirement model cleanly filter?

Script:

```python
from kailash_pact import GovernanceEngine, check_clearance
from kaizen.agents import MLAwareAgent
import kailash_ml as km

# Agent construction — tenant envelope is "acme enterprise" with D:M, T:M, R:Agent
agent = MLAwareAgent(tenant_id="acme")
tools: list[ToolSpec] = agent._build_ml_tools()

# Under the hood (per kaizen-ml §2.4.3 L187-200):
#   engines: tuple[EngineInfo, ...] = km.list_engines()
#   admissible = [e for e in engines if agent._is_clearance_admissible(e.clearance_level)]
# For acme's envelope (D:M, T:M, R:Agent):
#   - MLEngine.fit: (D:M, T:L) → all D≥M, T≥L held → admissible ✓
#   - MLEngine.register(stage="staging"): (D:M, T:H, R:Agent) → T:H > acme's T:M → REJECTED ✗
#   - FeatureStore.erase_tenant: (D:H, T:H, R:Human) → D:H > acme's D:M → REJECTED ✗
```

**Does the tuple-of-ClearanceRequirement cleanly map?** YES, on two counts:

1. **Axis-level composability.** §E11.1 L488-493 defines `ClearanceRequirement(axis, min_level)` as one axis + one minimum level, and §E11.1 L504 composes a tuple so "fit requires D:M AND T:L" is `(ClearanceRequirement("D","M"), ClearanceRequirement("T","L"))`. The kaizen-ml §2.4.3 L193 comment says: "Each `ClearanceRequirement(axis, min_level)` pair is validated independently; an engine is admissible only if EVERY requirement in its tuple holds for the tenant." That's the AND semantics an ML team actually needs.

2. **PACT envelope binding.** `pact-ml-integration-draft.md §1.2 L42` says PACT already speaks D/T/R + L/M/H via `ClearanceContext`, `ConstraintEnvelopeConfig`. The `_is_clearance_admissible` call at kaizen-ml §2.4.3 L191-195 reads each `ClearanceRequirement` and checks it against the envelope — no new PACT primitive types, no policy DSL extensions. The tuple shape is the transport; PACT's existing grammar is the decision surface. Clean.

**One practitioner-lens quibble.** §2.4.3 L196-199's filter returns `tuple(...)` — tuples of engines. The return annotation at L188 says `tuple[EngineInfo, ...]`. But for N>100 engines this is O(N × per-engine-check). Fine for v1.0.0 (N=18); worth noting in the v1.1 roadmap that clearance-admissibility caching per `(tenant_id, envelope_hash)` is needed if the registry grows past 50 engines. NOT blocking.

### Scenario 3: Senior DS wants to enumerate all 18 engines — does §E1.1 + `km.list_engines()` match?

Script:

```python
import kailash_ml as km

all_engines = km.list_engines()
print(f"kailash-ml {km.__version__} exposes {len(all_engines)} engines")

for e in all_engines:
    print(f"  {e.name:22s} tenant={'Y' if e.accepts_tenant_id else 'N'}  "
          f"tracker={'Y' if e.emits_to_tracker else 'N'}  "
          f"methods={len(e.signatures)}  "
          f"extras={e.extras_required}")
```

**Expected output per §E1.1:**

```
kailash-ml 1.0.0 exposes 18 engines
  MLEngine               tenant=Y  tracker=Y  methods=8   extras=()
  TrainingPipeline       tenant=Y  tracker=Y  methods=1   extras=()
  ExperimentTracker      tenant=Y  tracker=Y  methods=3   extras=()
  ModelRegistry          tenant=Y  tracker=Y  methods=4   extras=()
  FeatureStore           tenant=Y  tracker=Y  methods=4   extras=()
  InferenceServer        tenant=Y  tracker=Y  methods=3   extras=('grpc',)
  DriftMonitor           tenant=Y  tracker=Y  methods=3   extras=()
  AutoMLEngine           tenant=Y  tracker=Y  methods=1   extras=()
  HyperparameterSearch   tenant=Y  tracker=Y  methods=1   extras=()
  Ensemble               tenant=Y  tracker=Y  methods=2   extras=()
  Preprocessing          tenant=Y  tracker=Y  methods=2   extras=()
  FeatureEngineer        tenant=Y  tracker=Y  methods=3   extras=()
  ModelExplainer         tenant=Y  tracker=Y  methods=2   extras=()
  DataExplorer           tenant=Y  tracker=Y  methods=3   extras=()
  ModelVisualizer        tenant=Y  tracker=Y  methods=1   extras=()
  Clustering             tenant=Y  tracker=Y  methods=2   extras=()
  AnomalyDetection       tenant=Y  tracker=Y  methods=3   extras=()
  DimReduction           tenant=Y  tracker=Y  methods=2   extras=()
```

18 engines, methods per engine matching §E1.1's "Primary mutation methods audited" column. **§E11.3 MUST 4 correctly binds the Tier-2 test to this shape** ("per-engine public-method count specified in §E1.1").

**Clean walkthrough.** The only drift is the MED-R7-1 residuals — a DS reading §E11.1 L505's comment would expect `methods=8` on every row, then be surprised by the output. Fix the two residuals and this scenario has zero surprises.

### Scenario 4: Reproducibility chain (km.seed → km.train → km.reproduce → km.lineage) across tenants — single coherent story?

Script:

```python
import kailash_ml as km
from datetime import datetime

# Day 1 — original training run at acme
with km.track("baseline-churn", tenant_id="acme", actor_id="ds-42"):
    km.seed(42, cudnn_benchmark=False)   # §11.1 — sets _current_seed contextvar
    engine = km.MLEngine()
    engine.setup(df, target="churned")
    original = engine.fit(family="lightgbm")   # original.seed_report.seed == 42
    registered = await engine.register(original, name="churn-baseline", is_golden=True)
    # lineage: run → dataset → features → model_version

# Day 30 — CI: upstream lightgbm bumped 3.3.5 → 4.0.0. Reproduce + verify.
with km.track("baseline-churn-repro", tenant_id="acme"):
    reproduced = await km.reproduce(
        original.tracker_run_id,
        verify=True,    # rtol/atol gate per §12.1 MUST 3
    )   # internally: km.seed(42, ...) + engine.fit(... code from day-1 ...)

# Day 45 — PagerDuty incident: "what dataset was the golden run trained on?"
with km.track(tenant_id="acme"):   # ambient tenant via contextvar
    graph = await km.lineage(original.tracker_run_id)
    # LineageGraph with nodes: run, dataset, 3× feature_version, model_version
    datasets = [n for n in graph.nodes if n.kind == "dataset"]
    print(datasets[0].metadata["dataset_hash"])   # "sha256:abc..."
```

**Does the chain hold?** YES — four contexts, one coherent story:

- **km.seed** at `ml-engines-v2-draft.md §11.1 L1640`: module-level function, sets `_current_seed` contextvar (§11 L1698), emits warning on benchmark=True + fixed seed combo (L1710).
- **engine.fit** propagates `seed_report` into `TrainingResult.seed_report` (L1110 — the `SeedReport | None` field).
- **km.reproduce** at §12 L1735 reads the original run's `seed_report.seed`, calls `km.seed(seed_report.seed, ...)` BEFORE any other primitive (§12.1 MUST 1 L1767-1769), raises `ReproducibilityUnavailableError` if seed_report missing.
- **km.reproduce(verify=True)** per §12.1 MUST 3 L1781 is the release-CI gate; rtol/atol pinned per release.
- **km.lineage** at §15.8 L2163 resolves `tenant_id` from ambient `get_current_tenant_id()`; returns `LineageGraph` with tenant_id required on every node (`addendum §E10.2 L380`); cross-tenant reads raise `CrossTenantReadError` (`addendum §E10.3 MUST 2`).

**Tenant isolation across the chain.** acme's `km.track` ambient context sets tenant_id via contextvar. Every step reads the contextvar: reproduce's `km.seed` doesn't care about tenant_id; reproduce's engine dispatch per §15.2 MUST 1 routes through the tenant-scoped cached default engine; lineage reads same ambient contextvar. If a second tenant (e.g. "rival-co") simultaneously queries `km.lineage(original.tracker_run_id)` with their ambient tenant_id, the lineage subsystem raises `CrossTenantReadError` — the run belongs to acme, rival-co can't see it. **Coherent.**

**One reproducibility-lens quibble.** §11.1's warning on `cudnn_benchmark=True + fixed seed` (L1710) is the right warning, but a senior DS would also want `km.seed(42, ...)` to emit the seed AND PyTorch/numpy/hash-random states to the tracker run as structured events so `km.reproduce` can verify the ambient RNG state matches. §11.2 MUST 2 binds seed_report to TrainingResult; that's sufficient for fit-time reproducibility. Not blocking.

---

## Final verdict rationale

**CERTIFIED.** Three reasons, in load-bearing order:

1. **Phase-G surgically closed everything Round 6 flagged at the MUST clause level.** A11-NEW-2 at §E11.3 MUST 4 is correct (18 engines + per-engine count + all 17 support engines enumerated). HIGH-R6-A is gone (kml*agent*_ → *kml_agent*_ swept across DDL + indices + FK + §2.5 narrative + rationale prose). HIGH-R6-B is gone (kaizen-ml §2.4.2 L171 matches addendum §E11.1 L504 byte-for-byte). HIGH-R6-C is gone (§7.1.2 "Single-Format-Per-Row Invariant" is a cleanly-written paragraph answering the exact question a senior DS would ask). All 5 MEDs from Round-6's editorial sweep are gone. Phase-G's precision is practitioner-grade.

2. **The four production scenarios all complete with zero blockers.** Scenario 1 (dual-format register) is answered by §7.1.2's invariant + aggregate-at-read pattern + Shape-B/C v1.1 roadmap. Scenario 2 (Kaizen + PACT) uses existing PACT primitives (`ClearanceContext`, envelope) with tuple-of-ClearanceRequirement as the transport — no new PACT types needed. Scenario 3 (enumerate 18 engines) matches §E1.1 row-by-row with the correct per-engine method count. Scenario 4 (reproducibility chain) is coherent across km.seed → engine.fit → km.reproduce → km.lineage with ambient tenant_id + CrossTenantReadError as the structural defense. I would stake my team on this API surface.

3. **MED-R7-1 is a §5b miss at non-binding descriptive sites, not a contract drift.** The residual "8 methods per Decision 8" conflation at addendum L505 (dataclass comment) + kaizen-ml L172 (field-table) is the same bug-class as A11-NEW-2 but at 5× lower severity because neither site is a MUST clause or a Tier-2 test binding — they're descriptive prose. A reviewer reading §E11.3 MUST 4 (the authoritative clause) gets the correct contract; a reviewer reading the dataclass comment gets a misleading shorthand. Two one-line edits fix it. Not blocking CERTIFIED; flagged for the Round-8 editorial pass.

**What this looks like for 1.0.0-rc.** The spine is production-ready. The institutional-knowledge ratchet is: six rounds of senior-practitioner review have found four A11-class findings (A10-3 Round 4 HIGH → A11-NEW-1 Round 5 MED → A11-NEW-2 Round 6 MED → MED-R7-1 Round 7 MED). Severity is monotonically decreasing; scope is monotonically narrowing (cross-spec → cross-spec-sibling → within-file MUST → within-file descriptive). This is the profile of a converging specification. Ship 1.0.0-rc after MED-R7-1's 5-minute fix; final 1.0.0 after Round 8 confirms two consecutive clean rounds.

**Would I stake my team on kailash-ml 1.0.0 as specced NOW?** YES, conditional on (a) MED-R7-1's 5-minute fix at the two residual sites, (b) the two Round-4 roadmap-binding commits (v1.1-strategic + v1.1-hardening labels). These are ~10 minutes of spec work + 2 gh-label filings. The spine is production-ready. Every senior-grade feature (ClearanceRequirement composability, RegisterResult dict + shim, km.lineage ambient, EngineInfo introspection with deprecation metadata) is a differentiator that MLflow / W&B / Neptune / ClearML don't ship.

---

## Drafts audited (re-greped at audit time)

- `specs-draft/ml-engines-v2-draft.md` (2489 lines) — verified §2.1 MUST 5 (L215), §11-§12A chain (L1640-L1870), §15.8 km.lineage (L2163-2176), §15.9 **all** six-group ordering (L2180) + eager imports (L2249-2264).
- `specs-draft/ml-engines-v2-addendum-draft.md` (699 lines) — verified §E1.1 18-engine table (L22-43), §E11.1 dataclasses (L450-518) **including L505 residual comment**, §E11.3 MUST 4 (L602).
- `specs-draft/ml-registry-draft.md` (1143 lines) — verified §7.1 RegisterResult (L413-453), §7.1.1 shim (L455-486), **§7.1.2 single-format invariant (L488-507)**, §10 CAS.
- `supporting-specs-draft/kaizen-ml-integration-draft.md` (618 lines) — verified §2.4.1-§2.4.8 (L126-310) **including L172 residual field-table**, §5.2 _kml_agent_\* DDL (L446-492).
- `supporting-specs-draft/pact-ml-integration-draft.md` — verified §1.2 L42 "no new PACT primitive types" (ClearanceRequirement tuple maps onto existing ClearanceContext).
- `04-validate/approved-decisions.md` — verified Decision 8 (L15) = Lightning lock-in; L31 `_kml_*` prefix unification.
- `04-validate/round-6-senior-practitioner.md` — baseline for R7 delta.

Every line number cited re-greped at audit per `rules/testing.md` audit-mode re-derivation protocol. Prior-round line numbers not trusted; Phase-G edits shifted numbering throughout.
