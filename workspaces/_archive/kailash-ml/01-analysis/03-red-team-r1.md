# Red Team Round 1: kailash-ml Architecture

## Methodology

Adversarial analysis of the kailash-ml architecture, brief (`briefs/00-overview.md`), value proposition analysis (`02-value-proposition.md`), and all seven research files (`01-research/`). Each finding includes severity (CRITICAL / HIGH / MEDIUM / LOW), the specific concern, evidence from the research, and a recommended response.

---

## RT-R1-01: polars-only Contradicts Itself -- the pandas Shadow Dependency

**Severity**: MEDIUM

**Concern**: The brief states "kailash-ml NEVER converts to/from pandas internally." Research file `06-polars-ecosystem-analysis.md` reveals that `to_lgb_dataset()` converts to pandas for categorical support. LightGBM is in the base install. Therefore pandas IS a runtime dependency of the base install. The architecture claims polars-only while silently relying on pandas as a transitive dependency.

**Evidence**:

- Zero polars usage in the existing Kailash codebase (`01-existing-ml-code-audit.md` finding)
- sklearn, LightGBM, PyTorch, XGBoost, CatBoost, SHAP, ELI5, yellowbrick all expect pandas/numpy
- `to_lgb_dataset()` explicitly calls `features.to_pandas()` for categorical columns
- Any third-party ML library integration (SHAP, yellowbrick) requires `.to_pandas()` at the boundary
- polars-to-numpy conversion is near zero-copy for numeric data (5ms for 100K rows), so the conversion overhead is not the issue -- the honesty is

**Is polars-only a dealbreaker for ML practitioners used to pandas?** No. The conversion overhead is measurable but small (2-7.5% of training time per `06-polars-ecosystem-analysis.md` benchmarks). The interop module shields users from conversion mechanics. The real risk is not performance but ecosystem friction: users cannot copy-paste from sklearn tutorials, SHAP examples, or any existing pandas-based ML recipe. They must learn a new DataFrame API.

**Recommendation**:

1. Update the brief: "kailash-ml's user API is polars-only. Internally, LightGBM categorical support requires a pandas bridge. pandas is present as a transitive dependency but never exposed in user-facing APIs."
2. Include `to_pandas()` and `from_pandas()` in the interop module (currently not specified)
3. Document which third-party libraries require pandas and provide conversion recipes
4. Ship the interop module with published benchmarks so users can see the conversion cost

**Residual risk**: LOW (after honest documentation and pandas conversion utilities)

---

## RT-R1-02: 195MB Base Install -- Acceptable but the Incremental Story Matters

**Severity**: LOW

**Concern**: 195MB is comparable to mlflow (~200MB). But the relevant comparison is not "195MB vs other ML frameworks" -- it is "195MB on top of whatever the user already has." A user with `kailash` (15MB) + `kailash-dataflow` (5MB) who adds `kailash-ml` pulls in 175MB of new dependencies. Users in constrained environments (CI/CD pipelines, Docker layers, AWS Lambda's 250MB limit) will feel this.

**Evidence** (from `05-dependency-analysis.md`):

- Base breakdown: polars ~30MB, numpy ~25MB, scipy ~35MB, sklearn ~30MB, lightgbm ~5MB, plotly ~15MB, ONNX tools ~10MB, Kailash framework ~15MB
- Comparable frameworks: mlflow ~200MB, tensorflow ~500MB, torch CPU ~200MB
- Serverless risk: AWS Lambda 250MB unzipped limit leaves only 55MB for application code

**Is this acceptable?** Yes for the primary use case (ML development). No for inference-only deployments (serving a trained model should not require 195MB).

**Recommendation**:

1. Document incremental install sizes for common profiles: greenfield (195MB), existing kailash user (175MB incremental), user who already has sklearn+lightgbm (55MB incremental)
2. Consider an `inference-only` installation profile for v1.1: ModelRegistry + InferenceServer + onnxruntime (no sklearn/lightgbm/scipy/plotly)

**Residual risk**: LOW

---

## RT-R1-03: Lightning Escape Hatch Is Underspecified and Creates a Two-Path Maintenance Burden

**Severity**: HIGH

**Concern**: The brief mentions `TrainingPipeline(lightning=False)` as an escape hatch for raw PyTorch training loops. This is specified in one sentence and never elaborated. What does the escape hatch actually provide? If `lightning=False`, the user must supply their own training loop. But TrainingPipeline's value is lifecycle management: checkpointing, logging, model registration, distributed training, mixed precision. Without Lightning, who handles:

- Distributed training coordination?
- Mixed precision setup?
- Checkpointing and resume?
- Logging integration with DataFlow?
- Early stopping?

If the answer is "the user handles all of that," then `lightning=False` is not an escape hatch -- it is an eject button that removes most of TrainingPipeline's value. If the answer is "TrainingPipeline reimplements those without Lightning," then the complexity savings of using Lightning evaporate and you maintain two parallel DL training code paths.

**Evidence** (from `03-kaizen-integration-points.md` and the brief):

- Lightning's `Trainer` has 40+ parameters
- Lightning version compatibility with PyTorch is historically fragile
- Maintaining two code paths (Lightning + raw PyTorch) doubles the DL testing surface
- The escape hatch is mentioned once in the brief with zero specification

**Recommendation**:

1. Define exactly what `lightning=False` provides before implementation. Likely answer: TrainingPipeline handles model registration, metric logging to DataFlow, and ONNX export, but delegates the actual training loop to a user-provided callable `train_fn(data, config) -> model`. This is a clearly bounded contract.
2. Consider deferring the escape hatch to v1.1 and shipping Lightning-only in v1.0. This cuts the DL testing surface in half.
3. If shipped in v1, the escape hatch MUST be tested in CI with the same rigor as the Lightning path.

**Residual risk**: MEDIUM (with clear specification; HIGH without it)

---

## RT-R1-04: Guardrail 4 (Baseline Comparison) Doubles Compute Cost -- and Guardrail 1 Is Epistemically Weak

**Severity**: HIGH

**Concern**: Two of the 5 guardrails have design problems that the research does not address.

**Guardrail 4 (baseline comparison)**: "Pure algorithmic recommendation shown alongside agent recommendation" means every agent-augmented engine call runs TWO code paths. For AutoMLEngine, this means running full hyperparameter search algorithmically (the baseline) AND running agent-augmented search. If AutoML takes 30 minutes algorithmically, Guardrail 4 doubles that to 60 minutes. The user pays for the baseline even when using agents.

**Guardrail 1 (confidence scores)**: LLMs are notoriously poorly calibrated. A confidence score of 0.8 from an LLM does not mean 80% accuracy. ML practitioners will misinterpret these as calibrated probabilities, which they are not. The confidence output is the LLM's self-assessment -- it reflects linguistic certainty, not statistical validity.

**Evidence**:

- `03-kaizen-integration-points.md` confirms agents use the Delegate pattern with Signatures. The `confidence: float` OutputField is a standard Kaizen pattern -- no calibration mechanism exists.
- `02-value-proposition.md` acknowledges "Without [guardrails], it is a gimmick" but does not quantify the compute cost of Guardrail 4.
- LLM calibration research consistently shows that self-reported confidence scores are unreliable without temperature scaling or other post-hoc calibration.

**Recommendation**:

1. **Guardrail 4**: Refine the baseline to compare _recommendations_, not _results_. The baseline is "what the default algorithm would select" (e.g., LightGBM with default hyperparameters), computed in seconds -- NOT a full training run. The agent recommendation is compared against this default selection, not against a parallel full AutoML run.
2. **Guardrail 1**: Rename to `self_assessed_confidence` in the API. Add documentation: "This score reflects the LLM's self-assessment, not a calibrated probability. Use for relative ranking between recommendations, not as an absolute threshold."
3. **Guardrail 2 (cost budget)**: Make cost-per-token configurable via environment variables. Do not hardcode pricing.
4. **Guardrail 5 (audit trail)**: Batch audit writes (flush every N decisions or every T seconds) instead of per-decision database writes.

**Residual risk**: MEDIUM (after refining Guardrails 1 and 4)

---

## RT-R1-05: ONNX Bridge -- Failure Modes Are Analyzed but Version Transition UX Is Not

**Severity**: MEDIUM

**Concern**: The ONNX research (`07-onnx-bridge-feasibility.md`) is thorough. ~15% of models will fail ONNX export. The fallback (native Python inference) is correct. But the user experience around failure -- especially across model version transitions -- is undefined.

**Scenario**: A user trains a model, registers it (`onnx_status="success"`), deploys to Rust. Months later, they retrain with a slightly different architecture (add a custom layer). The new version fails ONNX export (`onnx_status="failed"`). The Rust deployment is now stale -- still serving the old ONNX model while the Python registry has a new version. The architecture does not define what happens here.

**Will ONNX bridge frustrate users?** Yes, for the ~15% of models that fail export. But frustration is manageable if failure is clear, expected, and well-communicated. Silent failures (Rust serving stale models) are the real danger.

**Evidence**:

- `07-onnx-bridge-feasibility.md`: ~85% weighted success rate, with PyTorch being the weakest (70-85%)
- The brief defines `onnx_status` field but does not define transition behavior between versions
- Failure Mode 5 (numeric precision drift) is particularly insidious -- the model exports, inference runs, but predictions differ subtly

**Recommendation**:

1. Define the ONNX version transition protocol: when a new version has `onnx_status="failed"` and the previous had `onnx_status="success"`, (a) Rust InferenceServer keeps serving the old version + emits WARNING, (b) Python InferenceServer serves the new version via native inference, (c) ModelRegistry marks this as an "ONNX-degraded" transition
2. Pre-flight check: before attempting export, check if the model type is in the known-supported list
3. Post-export validation: predict on 10 sample inputs with both native and ONNX, compare within tolerance (1e-4)
4. Clear Rust-side errors: "This model requires Python inference. Use the Python InferenceServer."

**Residual risk**: LOW (after defining transition protocol and improving failure UX)

---

## RT-R1-06: ModelRegistry "MLflow Compatible" Will Be Misinterpreted

**Severity**: MEDIUM

**Concern**: The brief says "MLflow MLmodel format v1 compatibility -- metadata round-trips through MLflow without data loss." This is a narrow claim (metadata format compatibility), but users will interpret "MLflow compatible" broadly. They will expect: listing kailash-ml models in the MLflow UI, serving with `mlflow models serve`, importing models logged with `mlflow.sklearn.log_model()`.

**Can ModelRegistry really be MLflow-compatible without becoming MLflow?** No. "Compatible" implies behavioral equivalence. What kailash-ml offers is "format-interoperable" -- it can read and write the same YAML file. The risk is that "v1.1: W&B, Neptune, ClearML compatibility" expands this into a full experiment tracking platform.

**Evidence**:

- MLflow has 12 years of development, 1000+ contributors, hundreds of model flavors
- `02-value-proposition.md` correctly states "ModelRegistry is focused on model lifecycle management, not experiment tracking"
- The brief plans W&B/Neptune/ClearML compatibility for v1.1 -- scope creep toward becoming an experiment tracking aggregator

**Recommendation**:

1. Replace "MLflow compatible" with "MLflow MLmodel format interoperable" in all documentation
2. Be surgically precise: "kailash-ml can (a) import a model from an MLflow registry, (b) export a model that MLflow can read. It does NOT require or replace a running MLflow tracking server."
3. W&B/Neptune/ClearML v1.1 should be EXPORT ONLY (write metrics/artifacts to these services). Not import, not bi-directional sync.
4. Anti-feature: kailash-ml MUST NOT grow an experiment tracking UI. That is MLflow/W&B territory.

**Residual risk**: LOW (with precise language and explicit scope limits)

---

## RT-R1-07: 9 Engines in v1 -- Scope Creep Risk Is the Dominant Threat

**Severity**: HIGH

**Concern**: This is the most significant risk in the entire architecture. 9 engines + 6 agents + protocols package + interop module + ONNX bridge = enormous surface area. The value proposition analysis already identifies a clear MVP of 5 engines and then recommends shipping all 9 anyway. The rationale ("each engine is 1-2 sessions") underestimates integration complexity.

**Evidence**:

- Each engine integrates with 1-3 other engines. With 9 engines, there are ~15 integration points.
- `02-value-proposition.md` identifies 5 core engines (TrainingPipeline, FeatureStore, ModelRegistry, InferenceServer, DriftMonitor) that cover the complete ML lifecycle
- The 4 deferred engines (AutoMLEngine, HyperparameterSearch, DataExplorer, FeatureEngineer) all depend on the core 5 -- deferral creates zero architectural debt
- Quantified risk: if each engine has 90% chance of shipping production-quality, probability of all 9 at quality = 0.9^9 = 39%
- "Mark as experimental" signals to users that the framework is incomplete -- worse than not shipping the engine at all

**What is the true MVP?** The value proposition already answered this: TrainingPipeline, FeatureStore, ModelRegistry, InferenceServer, DriftMonitor. These 5 engines cover features-to-train-to-register-to-serve-to-monitor. Everything else is a productivity enhancement.

**Recommendation**:

Ship v1.0 with the 5 core engines. Ship v1.1 (2-4 weeks later) with the remaining 4. This is the value proposition's own recommendation. Follow it. The benefits:

1. v1.0 ships with 5 polished, well-tested engines instead of 9 engines of mixed quality
2. The 4 deferred engines have a stable foundation to build on
3. Testing surface is manageable (5 engines x 3 frameworks = 15 combinations instead of 27)
4. v1.1 release creates a second launch moment for community engagement

If the decision is to ship all 9, then quality MUST be tiered explicitly: P0 (guaranteed production) for the core 5, P1 (beta) for AutoMLEngine and HyperparameterSearch, P2 (experimental) for DataExplorer and FeatureEngineer. No silent quality differences.

**Residual risk**: MEDIUM (with 5-engine MVP) or HIGH (with 9 engines and implicit quality variance)

---

## RT-R1-08: kailash-ml-protocols -- Right Solution but Protocol Design Must Be Finalized Before Implementation

**Severity**: MEDIUM

**Concern**: The protocol package approach is the standard Python solution for circular dependencies. The research (`05-dependency-analysis.md`) correctly identifies it as "worth the maintenance cost." But protocol interfaces are effectively permanent -- methods cannot be removed without breaking all three packages. The current brief defines protocols at a high level (`predict`, `get_metrics`, `trigger_retrain`) without validated method signatures.

**Is this the right circular dependency solution?** Yes. The alternatives (conditional imports everywhere, no type safety, or merging kailash-ml and kailash-kaizen) are all worse. A ~50KB protocol package with zero dependencies is the lowest-cost solution.

**Evidence**:

- `05-dependency-analysis.md`: "Protocol methods cannot be removed without breaking implementations. Only additive changes are safe."
- `03-kaizen-integration-points.md`: identifies specific call patterns between kailash-ml and kailash-kaizen but the protocol methods are not mapped to these patterns
- Unresolved design questions: Does `predict()` accept a single record or a batch? Does `get_metrics()` return all metrics or accept a filter? Does `trigger_retrain()` return synchronously or asynchronously?

**Recommendation**:

1. Before implementing kailash-ml-protocols, write the full Protocol classes with complete method signatures, type annotations, and docstrings
2. Review every protocol method against its actual call sites in both kailash-ml and kailash-kaizen integration code
3. Design conservatively: include only methods that are certain to survive v1 unchanged. Speculative methods can be added in v1.1.
4. Protocol design must be finalized in /todos, not discovered during /implement

**Residual risk**: LOW (with upfront protocol design review)

---

## RT-R1-09: Competitive Positioning -- Why Not Just Use MLflow + sklearn Directly?

**Severity**: MEDIUM

**Concern**: The value proposition analysis answers this honestly but does not state the positioning clearly enough. kailash-ml does not compete with MLflow, Feast, or Evidently individually. Each of those tools is more mature and feature-rich in its specific domain. kailash-ml's value is integration: a single package that provides the complete ML lifecycle within the Kailash ecosystem.

**What is the competitive landscape?**

- **MLflow** (experiment tracking + model registry): 17K+ GitHub stars, Databricks backing, massive community. kailash-ml ModelRegistry is a subset.
- **Feast** (feature store): established open-source feature store. kailash-ml FeatureStore is a subset.
- **Evidently** (drift monitoring): specialized and mature. kailash-ml DriftMonitor is a subset.
- **Kedro** (ML pipeline orchestration): lightweight, growing adoption. But lacks model serving and drift monitoring.

**Why use kailash-ml?** If you are already using DataFlow, Nexus, and Kaizen, kailash-ml gives you ML lifecycle management that is native to your stack -- zero additional infrastructure, shared database, integrated serving. If you are NOT using the Kailash ecosystem, raw MLflow + Feast + Evidently is a better choice.

**Recommendation**:

1. Do not position kailash-ml as competing with MLflow. Position it as "ML lifecycle for the Kailash ecosystem."
2. Be explicit in docs: "If you already use MLflow and Feast, and do not use the Kailash platform, those tools serve you well. kailash-ml is for teams building on Kailash who want native ML integration."
3. The value prop is "one package, one database, one serving layer" -- not "better than MLflow."

**Residual risk**: LOW (positioning is a documentation concern, not an architecture concern)

---

## RT-R1-10: Integration Testing Is Combinatorial -- No Prioritization Strategy Exists

**Severity**: HIGH

**Concern**: The brief specifies a 5-tier testing strategy but does not address the combinatorial explosion of engine-framework-backend combinations.

**Evidence**:

- 9 engines x 3 ML frameworks (sklearn, LightGBM, PyTorch) = 27 engine-framework combinations
- ~15 engine-to-engine integration points
- 3 DataFlow backends (SQLite, PostgreSQL, in-memory)
- 2 ONNX paths (export + inference) per model type
- ~30 ONNX model type combinations (per `07-onnx-bridge-feasibility.md`)
- Tier 3 tests take up to 5 minutes each. Full matrix: ~80 test dimensions x 5 min = 400 min = 6.5 hours

**How do you test 9 engines x 3 frameworks?** You do not test the full matrix on every PR. You define a critical path matrix.

**Recommendation**:

1. Define a **critical path test matrix** (15-20 combinations) that runs on every PR:
   - TrainingPipeline x {sklearn RandomForest, LightGBM, PyTorch MLP} x SQLite
   - FeatureStore x polars x SQLite
   - ModelRegistry x {sklearn, LightGBM} x SQLite (ONNX export + validation)
   - InferenceServer x {sklearn, LightGBM, ONNX runtime} x SQLite
   - DriftMonitor x sklearn x SQLite
   - End-to-end: train -> register -> serve -> check drift (sklearn + SQLite)
2. Define a **full matrix** that runs nightly:
   - All engine-framework combinations x SQLite
   - Core engines x PostgreSQL
   - All ONNX export paths
3. Define a **GPU matrix** that runs weekly:
   - PyTorch training with CUDA
   - Lightning distributed training
4. Document which combinations are tested and which are best-effort. Users need to know.

**Residual risk**: MEDIUM (with defined test matrix) or HIGH (without one)

---

## Summary Table

| #   | Finding                               | Severity | Core Question                              | Action Required                                                              |
| --- | ------------------------------------- | -------- | ------------------------------------------ | ---------------------------------------------------------------------------- |
| 1   | polars shadow pandas dependency       | MEDIUM   | Is polars-only a dealbreaker?              | No -- update docs to be honest, add pandas conversion utilities              |
| 2   | 195MB base install                    | LOW      | Is this acceptable?                        | Yes -- document incremental sizes, consider inference-only profile           |
| 3   | Lightning escape hatch                | HIGH     | Does it add more complexity than it saves? | Underspecified -- define contract before implementation or defer to v1.1     |
| 4   | Agent guardrails (cost + calibration) | HIGH     | Are they realistic?                        | Refine Guardrail 4 to compare recommendations not results; rename confidence |
| 5   | ONNX bridge version transitions       | MEDIUM   | Will this frustrate users?                 | Define transition protocol for ONNX status changes between versions          |
| 6   | MLflow "compatibility" claim          | MEDIUM   | Can it avoid becoming MLflow?              | Use "format interoperable" not "compatible"; enforce scope limit             |
| 7   | 9 engines scope                       | HIGH     | What is the true MVP?                      | Ship 5 core engines in v1.0, remaining 4 in v1.1                             |
| 8   | Protocol package design timing        | MEDIUM   | Is this the right solution?                | Yes -- but finalize method signatures before implementation                  |
| 9   | Competitive positioning               | MEDIUM   | Why not MLflow + sklearn?                  | Position as "ML for Kailash ecosystem" not "MLflow competitor"               |
| 10  | Integration test combinatorics        | HIGH     | How to test 9x3?                           | Define critical path (15-20 combos) and full nightly matrix                  |

## Convergence Assessment

4 HIGH findings require resolution before /todos:

1. **Finding 3** (Lightning escape hatch): Needs specification or deferral decision
2. **Finding 4** (Guardrail 4 cost, Guardrail 1 calibration): Needs design refinement
3. **Finding 7** (9 vs 5 engines): Needs explicit scope decision
4. **Finding 10** (test matrix): Needs prioritized test plan

The architecture is fundamentally sound. The core decisions (polars-only with interop, sklearn+LightGBM in base, protocols package, ONNX with graceful fallback) survive red team scrutiny. The risks concentrate in scope management (9 engines vs 5 MVP) and specification gaps (escape hatch, guardrail costs, version transitions, test strategy).

**Recommended path**: Resolve the 4 HIGH findings, then proceed to /todos with the 5-engine MVP as v1.0 scope.
