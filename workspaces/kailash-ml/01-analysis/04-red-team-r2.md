# Red Team Round 2: kailash-ml Analysis Phase

## Methodology

Round 2 performs three tasks: (1) verify that R1 resolutions actually address the findings, (2) stress-test cross-workspace integration points, and (3) deep-dive the kailash-ml-protocols package design. Each finding includes severity, evidence, and a verdict on whether the R1 resolution holds.

---

## Section 1: R1 Resolution Verification

### RT-R2-01: polars — pandas conversion utilities are necessary but not sufficient

**R1 finding**: RT-R1-01 (HIGH) — polars-only creates ML ecosystem friction.
**R1 resolution**: Add `to_pandas()` and `from_pandas()` to the interop module.

**Verdict**: PARTIALLY RESOLVED (residual: MEDIUM)

Adding pandas conversion utilities resolves the internal friction — users can bridge to third-party libraries (SHAP, ELI5, yellowbrick) via `to_pandas()`. But the resolution is silent on three practical issues:

1. **Discovery problem**: Users will not know they need `to_pandas()` until they hit an error. A SHAP `shap.Explainer(model, data)` call with a polars DataFrame will raise a cryptic TypeError, not a helpful "use `to_pandas()` for SHAP compatibility" message. The interop module exists but nothing guides users to it.

2. **Round-trip fidelity**: `to_pandas()` -> third-party operation -> `from_pandas()` must preserve types. polars `pl.Categorical` maps to pandas `pd.Categorical`, but the reverse is not guaranteed if the third-party library modifies the DataFrame (e.g., SHAP adds a column with a dtype that polars cannot represent). The interop module needs explicit round-trip tests with real third-party libraries — not just internal type mapping.

3. **Documentation scope**: The R1 resolution says "document which third-party libraries require pandas." This is necessary but unbounded — the ML ecosystem has hundreds of libraries. A more practical approach: document the top 5 use cases (SHAP, pandas-profiling/ydata-profiling, matplotlib direct, seaborn, yellowbrick) with copy-paste recipes, and add a generic "how to use any pandas-expecting library" section.

**Recommended actions**:

- Interop module: add explicit `to_pandas()` and `from_pandas()` with round-trip property tests
- Documentation: top-5 third-party library recipes + generic bridging guide
- Error handling: when a polars DataFrame is passed to a function that raises TypeError, consider wrapping common entry points (SHAP, matplotlib) with helpful error messages in a `kailash_ml.compat` module (v1.1, not v1)

---

### RT-R2-02: Agent guardrails — renaming and batching are cosmetic fixes

**R1 finding**: RT-R1-04 (HIGH) — 5 guardrails have implementation concerns.
**R1 resolution**: Rename "confidence" to `self_assessed_confidence`, batch audit writes.

**Verdict**: PARTIALLY RESOLVED (residual: MEDIUM)

The rename is cosmetic. Users who see `self_assessed_confidence: 0.82` will still treat it as a calibrated probability — the word "confidence" is the problem, regardless of the prefix. Naming alone does not change behavior.

More substantive issues remain:

1. **Guardrail 2 (cost budget)**: The R1 response says "make cost-per-token configurable." But cost-per-token is not just a config issue — it requires tracking which model was used per LLM call, looking up its price, and accumulating. The Delegate's `budget_usd` parameter handles this for a single Delegate run, but an AutoML session may invoke multiple Delegate runs. The `LLMCostTracker` mentioned in the Kaizen integration research is the right component, but it does not exist yet — it is a net-new implementation that must be designed, not just configured.

2. **Guardrail 3 (human approval)**: The R1 response says "provide both sync and async approval patterns." The PendingApproval pattern is architecturally clean but needs careful thought about timeout behavior. What happens if a user starts an AutoML session with `auto_approve=False`, the agent proposes an action, and the user does not respond for 30 minutes? Does the session hang? Timeout and fall back to algorithmic? The timeout policy must be specified.

3. **Guardrail 5 (audit trail batching)**: Batching audit writes (collect N decisions, flush periodically) is correct. But batching introduces a data loss window — if the process crashes between flushes, recent agent decisions are lost. This is acceptable for audit trails (they are informational, not transactional), but the trade-off should be documented. Batch size and flush interval should be configurable, not hardcoded.

**Recommended actions**:

- Rename `confidence` to `llm_self_assessment` (removes the loaded word "confidence" entirely)
- Design `LLMCostTracker` as a first-class class with per-model pricing config via `.env` or YAML
- Specify `PendingApproval` timeout: default 10 minutes, configurable, falls back to algorithmic on timeout
- Document the audit batching data-loss window and make batch size/flush interval configurable

---

### RT-R2-03: MLflow scope limit — enforceable but needs an explicit anti-feature list

**R1 finding**: RT-R1-06 (HIGH) — ModelRegistry risks feature creep toward MLflow.
**R1 resolution**: Explicit scope limit — read/write MLmodel YAML only, W&B/Neptune as export-only.

**Verdict**: RESOLVED (residual: LOW)

The scope limit is clear and enforceable. The four-point response (v1: MLmodel YAML only; "compatible" means metadata round-trips; W&B/Neptune export-only; no experiment tracking UI) is precise enough to be tested against.

However, enforcement requires an explicit anti-feature list — things ModelRegistry MUST NOT do — documented in the codebase, not just in analysis docs. Without this, future sessions will face the same scope pressure and may not have the R1 context.

**Recommended actions**:

- Create a `ModelRegistry Anti-Features` section in the architecture doc or a dedicated rule
- Anti-features: (1) no experiment tracking, (2) no artifact logging beyond model files, (3) no model deployment management (InferenceServer handles this), (4) no UI/dashboard, (5) no MLflow server compatibility (only file format)
- W&B/Neptune/ClearML: defer to v1.1 as originally specified; do not begin until v1 core is stable

---

### RT-R2-04: Quality tiering — reduces perceived risk but not actual risk

**R1 finding**: RT-R1-07 (HIGH) — 9 engines + 6 agents, P(all production quality) = 39%.
**R1 resolution**: P0/P1/P2 quality tiering.

**Verdict**: PARTIALLY RESOLVED (residual: MEDIUM)

Quality tiering is a communication strategy, not a risk mitigation strategy. It sets user expectations (good), but it does not change the probability of a P0 engine having a defect. The math is the same: 5 P0 engines, each at 90% quality = 0.9^5 = 59% chance all P0 engines are production-quality.

The tiering is still the right approach — it focuses testing effort on P0 engines and sets honest expectations for P2. But two gaps remain:

1. **P2 engines shipping as `@experimental` need a promotion path**. What are the criteria for promoting DataExplorer and FeatureEngineer from experimental to production? Without criteria, they stay experimental indefinitely. Propose: "promote to production when (a) 3 integration tests cover the engine's core flows, (b) 2 real-world users have validated it, (c) no open bugs above LOW severity."

2. **P1 engines (HyperparameterSearch, AutoMLEngine) are the riskiest tier**. They are "production with caveats" but they depend on agent guardrails (AutoML) and Bayesian optimization (HyperSearch) — both are complex. If implementation time runs short, P1 engines should be demoted to P2 rather than shipped with hidden quality gaps. The journal entry (0004) asks this question but does not answer it.

3. **The 6 agents are not tiered**. The quality tiering applies to engines but all 6 agents are implied to ship in v1. If agent guardrails (RT-R2-02) prove harder than expected, which agents can be deferred? Propose: DataScientistAgent and RetrainingDecisionAgent are P0 (core workflow); ModelSelectorAgent and ExperimentInterpreterAgent are P1 (AutoML support); FeatureEngineerAgent and DriftAnalystAgent are P2 (optional augmentation).

**Recommended actions**:

- Define promotion criteria for P2 engines
- Define demotion criteria for P1 engines (what triggers demotion to P2?)
- Apply quality tiering to agents, not just engines

---

## Section 2: Cross-Workspace Integration

### RT-R2-05: kailash-ml-protocols must be released first — minimum viable surface

**Severity**: HIGH

kailash-ml-protocols is on the critical path for both kailash-ml and kailash-align. The cross-workspace synthesis identifies this as Phase 0 (1 session). But "release first" means the protocol surface must be correct on the first try — protocol methods cannot be removed in v1.x without breaking consumers.

**Minimum viable protocol surface** (exhaustive list):

```python
# kailash_ml_protocols/protocols.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class MLToolProtocol(Protocol):
    """Tools that kailash-kaizen agents call via MCP to access ML capabilities."""
    async def predict(self, model_name: str, features: dict) -> dict: ...
    async def get_metrics(self, model_name: str, version: str | None = None) -> dict: ...
    async def get_model_info(self, model_name: str) -> dict: ...

@runtime_checkable
class AgentInfusionProtocol(Protocol):
    """Protocol for agent-augmented engine methods."""
    async def suggest_model(self, data_profile: dict, task_type: str) -> dict: ...
    async def suggest_features(self, data_profile: dict, existing_features: list[str]) -> dict: ...
    async def interpret_results(self, experiment_results: dict) -> dict: ...
    async def interpret_drift(self, drift_report: dict) -> dict: ...


# kailash_ml_protocols/schemas.py
from dataclasses import dataclass

@dataclass
class FeatureSchema:
    name: str
    features: list[FeatureField]
    entity_id_column: str
    timestamp_column: str | None = None

@dataclass
class FeatureField:
    name: str
    dtype: str  # "int64", "float64", "utf8", "bool", "datetime", "categorical"
    nullable: bool = True
    description: str = ""

@dataclass
class ModelSignature:
    input_schema: FeatureSchema
    output_columns: list[str]
    output_dtypes: list[str]
    model_type: str  # "classifier", "regressor", "ranker"

@dataclass
class MetricSpec:
    name: str  # "accuracy", "f1", "rmse", "auc", etc.
    value: float
    split: str = "test"  # "train", "val", "test"
    higher_is_better: bool = True
```

**What was removed from the R1 spec**: `trigger_retrain()` from `MLToolProtocol`. Retraining is a complex operation that should not be a simple protocol call — it requires configuration (which data, which hyperparameters, which model version to base on). It belongs in kailash-ml's TrainingPipeline API, not in a cross-package protocol. Agents that want to trigger retraining should call a kailash-ml-specific API, not a protocol method.

**What was added**: `get_model_info()` in `MLToolProtocol` and `interpret_drift()` in `AgentInfusionProtocol`. These were implicit in the architecture but not listed in the R1 spec. They are needed for DriftAnalystAgent and for MCP platform server `kaizen.test_agent` flows that need to look up model metadata.

**Risk**: If `ModelSignature` does not capture enough information for kailash-align's `AdapterRegistry`, the protocol must be extended before kailash-align can start. `AdapterVersion` references `base_model_id` and `lora_config` — neither is in `ModelSignature`. This means either (a) `ModelSignature` is extended with optional LLM-specific fields, or (b) kailash-align defines its own `AdapterSignature` that references `ModelSignature`. Option (b) is cleaner — no LLM-specific fields in the generic protocol.

**Recommended actions**:

- Remove `trigger_retrain()` from MLToolProtocol
- Add `get_model_info()` to MLToolProtocol
- Add `interpret_drift()` to AgentInfusionProtocol
- kailash-align defines `AdapterSignature` separately, referencing `ModelSignature`
- Release protocols package before any engine implementation begins

---

### RT-R2-06: AdapterRegistry extends ModelRegistry — required interface surface

**Severity**: HIGH

kailash-align's `AdapterRegistry` extends `ModelRegistry` via class inheritance. The architecture doc shows `class AdapterRegistry(ModelRegistry)`. This means ModelRegistry must expose stable methods that AdapterRegistry overrides or calls via `super()`.

**Required ModelRegistry methods for AdapterRegistry**:

| Method                                                              | Used By AdapterRegistry                                                                                                     | How             |
| ------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- | --------------- |
| `register_model(name, artifact_path, metrics, feature_schema, ...)` | `register_adapter()` calls `super().register_model()` then adds adapter-specific fields                                     | Extension       |
| `get_model(name, version?)`                                         | `get_adapter()` wraps with adapter-specific fields                                                                          | Extension       |
| `list_models(filter?)`                                              | `list_adapters()` filters by adapter type                                                                                   | Extension       |
| `promote_model(name, version, target_stage)`                        | Used directly for adapter stage transitions                                                                                 | Inherited       |
| `get_model_versions(name)`                                          | Used directly for adapter version listing                                                                                   | Inherited       |
| `_store` / DataFlow access                                          | AdapterRegistry creates additional DataFlow models (`AlignAdapter`, `AlignAdapterVersion`) using the same DataFlow instance | Internal access |

**Critical design question**: Should `ModelRegistry` use composition or inheritance for extension?

- **Inheritance** (current plan): `AdapterRegistry(ModelRegistry)` — simpler, but any change to ModelRegistry's internal structure breaks AdapterRegistry. ModelRegistry's `__init__` parameters, internal state, and private methods become part of AdapterRegistry's contract.
- **Composition**: `AdapterRegistry` holds a `ModelRegistry` instance and delegates — more robust to changes, but requires explicitly defining which methods are delegated.

**Recommendation**: Keep inheritance but explicitly mark ModelRegistry's extension points. Define a `ModelRegistryBase` class in kailash-ml-protocols with abstract methods that both ModelRegistry and AdapterRegistry implement. This gives AdapterRegistry a stable contract without depending on ModelRegistry's implementation details.

Alternatively, if this is too complex for v1, use inheritance with an integration test: `test_adapter_registry_against_model_registry_interface()` that verifies all required methods exist and have compatible signatures.

**Recommended actions**:

- Document ModelRegistry's public API in kailash-ml-protocols as a non-abstract reference (not a Protocol — actual class would be too heavy)
- At minimum, freeze these method signatures before kailash-align starts: `register_model`, `get_model`, `list_models`, `promote_model`, `get_model_versions`
- Add integration test in kailash-align that imports ModelRegistry and verifies method signatures match expectations

---

### RT-R2-07: DataFlow DerivedModelEngine and FeatureStore — undesigned dependency

**Severity**: MEDIUM

The cross-workspace synthesis identifies a soft dependency: kailash-ml's FeatureStore could use DataFlow's DerivedModelEngine for materialized feature views. The dataflow-enhancements brief explicitly mentions this: "DerivedModelEngine blocks kailash-ml FeatureStore."

But this dependency is undesigned. Nowhere in the kailash-ml architecture does FeatureStore reference DerivedModelEngine. The research files describe FeatureStore using Express API + ConnectionManager for storage. DerivedModelEngine is not mentioned.

**Analysis**:

DerivedModelEngine provides: define a computation as a Python function, attach it to source DataFlow models, refresh on schedule/manual/change. FeatureStore's `compute_features(schema, data)` does something similar — it computes feature values from source data and stores them.

The overlap is real but the use cases differ:

- **DerivedModelEngine**: General-purpose computed columns/views. Refresh is model-scoped (when source model changes).
- **FeatureStore**: ML-specific feature computation. Refresh is entity-scoped (recompute features for specific entities). Needs point-in-time retrieval. Needs polars-native output.

FeatureStore SHOULD NOT depend on DerivedModelEngine in v1. The abstraction mismatch (model-scoped vs entity-scoped, DataFlow dicts vs polars DataFrames) would force FeatureStore into contortions. FeatureStore should use DataFlow for storage but implement its own computation and refresh logic.

In v2, a possible integration: DerivedModelEngine provides the scheduled refresh mechanism, and FeatureStore registers its computations as DerivedModels. This would eliminate duplicate scheduling code. But this is an optimization, not a v1 requirement.

**Recommended actions**:

- Remove "blocks kailash-ml FeatureStore" from the dataflow-enhancements dependency description — it is a soft enhancement, not a blocker
- FeatureStore implements its own computation and storage in v1
- Track DerivedModel-FeatureStore integration as a v2 optimization

---

### RT-R2-08: MCP platform server `kaizen.list_agents` — will it discover kailash-ml agents?

**Severity**: MEDIUM

The MCP platform server's `kaizen.list_agents()` tool scans for `BaseAgent` subclasses and `Delegate` instances via AST-based static analysis (since the MCP server runs as a separate process and cannot access runtime registries — GAP-2 in the MCP analysis).

kailash-ml's 6 agents (DataScientistAgent, FeatureEngineerAgent, etc.) are Kaizen `BaseAgent` subclasses with Signatures. They live in `packages/kailash-ml/src/kailash_ml/agents/`. The MCP platform server scans `project_root` for agent definitions.

**The problem**: The MCP server's `kaizen` contributor scans the project's source for `BaseAgent` subclasses. But kailash-ml agents live in an _installed package_ (`kailash_ml.agents`), not in the project's source tree. The AST scanner only scans `project_root` — it does not scan site-packages.

**Two scenarios**:

1. **Project IS kailash-py monorepo**: The MCP scanner finds agents in `packages/kailash-ml/src/kailash_ml/agents/`. This works because the source is in the project tree.

2. **Project USES kailash-ml as an installed dependency**: The MCP scanner scans the user's project source but kailash-ml agents are in site-packages. The scanner does not find them. `kaizen.list_agents()` returns only the user's custom agents, not kailash-ml's built-in agents.

Scenario 2 is the common case for end users. kailash-ml agents would be invisible to the MCP platform server.

**Possible resolutions**:

- (A) The `kaizen` contributor also scans installed packages for agents that declare themselves as discoverable (via entry points or a registry file). This adds complexity but enables discovery of framework-provided agents.
- (B) kailash-ml registers its agents in a `kailash_ml.agent_registry` that the Kaizen contributor can import at runtime (not AST scanning). This requires the MCP process to import kailash-ml, which adds startup weight.
- (C) Accept that `kaizen.list_agents()` returns only project-defined agents. Framework agents are documented, not discovered. This is simpler but less useful.

**Recommendation**: Option (C) for v1. Document kailash-ml agents in the `platform_map()` response under a `framework_agents` key (statically defined, no scanning needed). Option (A) or (B) for v2.

**Recommended actions**:

- For v1: `platform_map()` includes a static `framework_agents` section listing agents from installed kailash packages (read from package metadata, not AST scanning)
- `kaizen.list_agents()` scans project source only — clearly documented as "project agents, not framework agents"
- Track framework agent discovery as a v2 feature for the MCP platform server

---

## Section 3: Deep Dive — kailash-ml-protocols Package

### RT-R2-09: How thin can protocols really be?

**Severity**: LOW (design issue, not risk)

The R1 dependency analysis estimates ~50KB. The actual content:

```
kailash_ml_protocols/
    __init__.py           # 20 lines (re-exports)
    protocols.py          # ~60 lines (2 Protocol classes, 7 methods total)
    schemas.py            # ~80 lines (3 dataclasses, 1 helper)
    py.typed              # 0 lines (PEP 561 marker)
```

**Total: ~160 lines of code, <10KB source, <50KB wheel.**

Dependencies: Python 3.10+ standard library only (`typing`, `dataclasses`). Zero pip dependencies.

This is genuinely thin. The maintenance burden is version coordination, not code complexity.

### RT-R2-10: What happens when a protocol method needs to change in v1.x?

**Severity**: MEDIUM

Protocol methods are structural contracts. Once `MLToolProtocol.predict(model_name: str, features: dict) -> dict` is released, every implementation must provide it.

**Adding a method**: Safe within v1.x. Add `get_feature_importance()` to `MLToolProtocol`. Existing implementations that do not implement it will fail `isinstance(obj, MLToolProtocol)` checks if the protocol is `@runtime_checkable`. This is acceptable — the new method is used by new code that expects it.

**Changing a method signature**: Breaking. `predict(model_name, features, options=None)` changes the contract. Existing callers pass 2 args and work. New callers pass 3 args and fail against old implementations.

**Mitigation**: Use `**kwargs` for extensibility in the initial design? No — this defeats the purpose of typed protocols. Better approach: design method signatures with an `options: dict | None = None` parameter from the start for any method that might need future configuration. This is a common pattern in Google's protobuf APIs.

**Removing a method**: Breaking. Never allowed in v1.x. Deprecated methods must remain with a deprecation warning until v2.

**Practical assessment**: The protocols are small (7 methods across 2 protocols). The risk of needing to change a method signature in v1.x is low if the initial design is conservative. The recommended MVP surface (RT-R2-05) is intentionally minimal.

### RT-R2-11: Is there a simpler alternative to a protocols package?

**Severity**: LOW (architecture review)

**Alternative 1: Duck typing (no protocols package)**

kailash-ml defines its methods. kailash-kaizen calls them via `getattr(obj, "predict")`. No shared contract. No type safety.

**Problem**: Type checkers (mypy, pyright) cannot verify the interface. Runtime errors instead of static errors. The "duck typing everywhere" alternative from the dependency analysis is strictly worse.

**Alternative 2: `typing.Protocol` in kailash-ml itself**

kailash-ml defines `MLToolProtocol` in `kailash_ml.protocols`. kailash-kaizen depends on kailash-ml for the type definition.

**Problem**: This is the original circular dependency. kailash-kaizen would depend on kailash-ml at install time, and kailash-ml already depends on kailash-kaizen for agents. The whole point of the protocols package is to break this cycle.

**Alternative 3: `typing.Protocol` in kailash-kaizen itself**

kailash-kaizen defines the protocol. kailash-ml implements it without importing it (`typing.Protocol` supports structural subtyping).

**Problem**: The protocol defines ML-specific schemas (`FeatureSchema`, `ModelSignature`) that do not belong in kailash-kaizen. Kaizen is a general-purpose agent framework, not an ML framework. Putting ML schemas in Kaizen pollutes its API surface.

**Alternative 4: Entry points / plugin system**

kailash-ml registers capabilities via `setuptools` entry points. kailash-kaizen discovers them at runtime. No shared types.

**Problem**: Entry points are string-based discovery. They find modules but don't define contracts. You still need shared types for the actual interface.

**Verdict**: The protocols package is the correct architecture. All alternatives are worse. The ~50KB cost and version coordination overhead are the minimum price for a clean dependency DAG with type safety.

---

## Section 4: New Findings

### RT-R2-12: FeatureStore point-in-time queries and DataFlow Express limitations

**Severity**: MEDIUM

Journal entry 0005 identifies that DataFlow Express cannot handle FeatureStore's point-in-time queries (`WHERE created_at <= ? ORDER BY created_at DESC LIMIT 1`). The resolution is to use ConnectionManager directly.

This is correct but introduces a maintenance risk: FeatureStore becomes a mixed-layer engine (Express for metadata, ConnectionManager for feature data). Mixed-layer engines must follow ALL infrastructure-sql rules (validate identifiers, use transactions, canonical `?` placeholders, parameterized queries).

The risk is not the mixed-layer pattern itself — it is that future maintainers may extend FeatureStore's raw SQL queries without awareness of `rules/infrastructure-sql.md`. The solution: FeatureStore's ConnectionManager usage should be encapsulated in a single internal module (`kailash_ml/_feature_sql.py`) that serves as the only raw SQL touchpoint, making it auditable.

### RT-R2-13: Nexus dependency is mandatory but should be lazy

**Severity**: LOW

kailash-ml lists `kailash-nexus` as a required dependency (for InferenceServer endpoint registration). But users who only train models (no serving) still pull in FastAPI, uvicorn, and the Nexus package.

Research file 04-nexus-integration-points.md notes: "Consider making Nexus integration lazy (import only when `register_endpoints()` is called)."

This is straightforward: keep `kailash-nexus` in the dependency list (it is small, ~5MB) but make InferenceServer's Nexus import lazy. If the user never calls `register_endpoints()`, Nexus is never imported and FastAPI never starts. This is the same pattern as DataFlow's lazy driver imports.

---

## Summary

| Finding                              | Severity | R1 Status                      | R2 Verdict                                                            |
| ------------------------------------ | -------- | ------------------------------ | --------------------------------------------------------------------- |
| RT-R1-01: polars pandas conversion   | HIGH     | Adding to_pandas/from_pandas   | PARTIALLY RESOLVED — needs round-trip tests, recipes, discovery       |
| RT-R1-04: Agent guardrails           | HIGH     | Rename confidence, batch audit | PARTIALLY RESOLVED — LLMCostTracker undesigned, timeout unspecified   |
| RT-R1-06: MLflow scope               | HIGH     | Explicit scope limit           | RESOLVED — add anti-feature list to codebase                          |
| RT-R1-07: 9 engines scope            | HIGH     | P0/P1/P2 tiering               | PARTIALLY RESOLVED — no promotion criteria, agents untiered           |
| RT-R2-05: Protocols package MVP      | HIGH     | —                              | NEW — minimum viable surface defined, trigger_retrain removed         |
| RT-R2-06: AdapterRegistry interface  | HIGH     | —                              | NEW — 5 methods must be frozen before kailash-align starts            |
| RT-R2-07: DerivedModel/FeatureStore  | MEDIUM   | —                              | NEW — soft dependency, not a v1 blocker                               |
| RT-R2-08: MCP agent discovery        | MEDIUM   | —                              | NEW — framework agents invisible in user projects; v1: static listing |
| RT-R2-09: Protocols package thinness | LOW      | —                              | CONFIRMED — ~160 lines, genuinely thin                                |
| RT-R2-10: Protocol evolution         | MEDIUM   | —                              | NEW — add `options: dict` parameter for future extensibility          |
| RT-R2-11: Protocol alternatives      | LOW      | —                              | CONFIRMED — protocols package is the correct architecture             |
| RT-R2-12: FeatureStore mixed SQL     | MEDIUM   | —                              | NEW — encapsulate raw SQL in single internal module                   |
| RT-R2-13: Nexus lazy import          | LOW      | —                              | NEW — lazy import in InferenceServer                                  |

### Open R1 findings not re-examined (status unchanged from R1)

| Finding                         | R1 Severity | R1 Status                                  | R2 Note                                    |
| ------------------------------- | ----------- | ------------------------------------------ | ------------------------------------------ |
| RT-R1-02: 195MB base install    | MEDIUM      | Acceptable                                 | No change — 195MB is standard for ML       |
| RT-R1-03: Lightning two-path    | MEDIUM      | Test both, consider deferring escape hatch | No new information                         |
| RT-R1-05: ONNX failure UX       | MEDIUM      | Add proactive warnings                     | No new information                         |
| RT-R1-08: Protocol coordination | MEDIUM      | Conservative design                        | Addressed more deeply in RT-R2-05/RT-R2-10 |
| RT-R1-09: No polars precedent   | MEDIUM      | Centralize conversion                      | Subsumed by RT-R2-01 (polars interop)      |

### Overall Assessment

R1 identified the right risks. R1 resolutions are directionally correct but in several cases are communication fixes (naming, tiering labels) rather than engineering fixes (new components, explicit contracts, timeout policies). R2 identifies the engineering gaps that remain:

1. **kailash-ml-protocols MVP surface** must be defined and frozen before implementation begins (Phase 0 blocker)
2. **ModelRegistry public API** must be explicitly documented for AdapterRegistry extension (Phase 0 blocker)
3. **LLMCostTracker** is a net-new component, not a configuration change
4. **Agent quality tiering** is needed alongside engine quality tiering
5. **FeatureStore raw SQL** should be encapsulated for auditability

No CRITICAL findings. The architecture is sound. The gaps are implementation-level details, not fundamental design flaws.
