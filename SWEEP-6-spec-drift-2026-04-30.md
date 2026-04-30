# Sweep 6: spec-vs-code drift — 2026-04-30

Audit scope: 73 spec files in `specs/`. Mechanical AST/grep + `inspect.signature` verification, never file-existence proxies (per `skills/spec-compliance/SKILL.md`).

Last full pre-audit was kailash-ml-audit (2026-04-23, ML-only). Non-ML domains have not been swept end-to-end since. This sweep sampled all domain heads and 2-3 deep-dive invariants per domain. Some specs were not opened (see "Domains NOT audited" below); findings here are a lower bound.

## Critical findings (call-out)

**HIGH-1 — kaizen-llm-deployments.md is significantly out-of-sync with code.** The spec advertises `LlmClient.complete()` and `LlmClient.stream_completion()` as the primary surface (cited in §6 Security Contract as the emission point for `llm.request.start` / `llm.request.ok` / `llm.request.error`). Neither method exists on `LlmClient`. The class only exposes `from_deployment`, `from_deployment_sync`, `from_env`, `with_deployment`, `embed`, `redact_request_messages`, `classification_policy`, `deployment`. This is a documented-but-not-implemented public surface — the load-bearing kwarg-plumbing rule (`security.md` § Multi-Site Kwarg Plumbing) cannot bind because the call sites don't exist. Spec also names factories `LlmDeployment.bedrock`, `.vertex`, `.azure`, `.gemini`, `.from_uri`, `.from_env` that do NOT exist (real factories are `bedrock_claude/cohere/llama/mistral/titan`, `vertex_claude/vertex_gemini`, `azure_entra/azure_openai`, `google`).

**HIGH-2 — kaizen-core.md (and project `rules/patterns.md`) advertises `from kaizen.core import BaseAgent`, but the import raises ImportError.** `BaseAgent` lives at `kaizen.core.base_agent.BaseAgent`; not re-exported through `kaizen.core.__init__.py`. The Quick Start in `rules/patterns.md` shows `from kaizen.core import BaseAgent, Signature, InputField, OutputField` — that line crashes today on every fresh install. (`Signature/InputField/OutputField` ARE re-exported from top-level `kaizen` but NOT from `kaizen.core`.)

## Summary

| Severity | Count |
| -------- | ----- |
| CRIT     | 0     |
| HIGH     | 7     |
| MED      | 6     |
| LOW      | 4     |

## Findings

### [HIGH] [kaizen] LlmClient missing complete/stream_completion methods

**Spec:** `specs/kaizen-llm-deployments.md` §6 Security Contract / §Observability Contract (lines 116, 146-160) — names `LlmClient.complete` and `LlmClient.stream_completion` as the primary emission surface for canonical structured logs.
**Source:** `packages/kailash-kaizen/src/kaizen/llm/client.py:79` — class `LlmClient` exposes only `from_deployment`, `from_deployment_sync`, `from_env`, `with_deployment`, `embed`, `redact_request_messages`, `classification_policy`, `deployment`. Neither `complete` nor `stream_completion` is defined.
**Disposition:** FILE-ISSUE. This is the primary user-facing API of the #498 abstraction. Either spec is aspirational and code is half-built, or the methods migrated to a different name. Cross-SDK parity at risk because spec calls these load-bearing for cross-language log-field stability.
**Evidence:** `dir(LlmClient)` returned `['classification_policy', 'deployment', 'embed', 'from_deployment', 'from_deployment_sync', 'from_env', 'redact_request_messages', 'with_deployment']`.
**Why this matters:** Every reader of the spec sees `LlmClient.complete()` advertised; every implementation attempt against today's code fails with `AttributeError`. Same failure-mode class as `zero-tolerance.md` Rule 6 (Implement Fully) — half-implemented public surface.

### [HIGH] [kaizen] LlmDeployment factory names drift from spec

**Spec:** `specs/kaizen-llm-deployments.md` §Preset Catalog (lines 16-78) names presets `LlmDeployment.bedrock(...)`, `.vertex(...)`, `.azure(...)`, `.gemini(...)`, plus class methods `LlmDeployment.from_uri()` and `LlmDeployment.from_env()`.
**Source:** `packages/kailash-kaizen/src/kaizen/llm/deployment.py:287` — actual factories are `bedrock_claude/cohere/llama/mistral/titan`, `vertex_claude/vertex_gemini`, `azure_entra/azure_openai`, `google`. No `from_uri` or `from_env` classmethod on `LlmDeployment`.
**Disposition:** FILE-ISSUE. Either spec needs updating to match the per-model factory split, or code needs the higher-level convenience factories. Spec mentions 24 presets total; code's per-model factory pattern is plausibly correct but spec must catch up.
**Evidence:** `dir(LlmDeployment)` returned the per-model factory names listed above; no `bedrock`, `vertex`, `azure`, `gemini`, `from_uri`, or `from_env`.
**Why this matters:** Spec is the contract; users copy spec snippets. `LlmDeployment.bedrock(...)` raises `AttributeError`. § Migration shows `from kaizen.llm import LlmDeployment` example using non-existent API.

### [HIGH] [kaizen] kaizen.core does not re-export BaseAgent / Signature / InputField / OutputField

**Spec:** `specs/kaizen-core.md` §3 BaseAgent and project `rules/patterns.md` § Kaizen show `from kaizen.core import BaseAgent, Signature, InputField, OutputField` as the canonical import.
**Source:** `packages/kailash-kaizen/src/kaizen/core/__init__.py` — `dir(kaizen.core)` returns `['Agent', 'AgentManager', 'ContextFile', 'Kaizen', 'KaizenConfig', 'KaizenOptions', 'MemoryProvider', 'OptimizationEngine', ...]`. No `BaseAgent`, `Signature`, `InputField`, `OutputField`. Real path is `from kaizen.core.base_agent import BaseAgent`.
**Disposition:** FIX-NOW (one-line addition to `kaizen/core/__init__.py` re-export). Or update spec to point users at `kaizen.core.base_agent`. The `rules/patterns.md` snippet IS the canonical Quick Start; it crashes on every fresh install.
**Evidence:** `from kaizen.core import BaseAgent` → `ImportError: cannot import name 'BaseAgent' from 'kaizen.core'. Did you mean: 'CoreAgent'?`
**Why this matters:** This is the single line every Kaizen agent author writes first. The spec/rule promise is a public-API contract; the failure is silent until the user tries the import. `orphan-detection.md` Rule 6 — module-scope imports must be re-exported.

### [HIGH] [ml] kailash_ml.**all** contains symbols not documented in spec §15.9

**Spec:** `specs/ml-engines-v2.md` §15.9 `kailash_ml.__all__` Canonical Ordering (lines 2188-2245) lists 49 symbols across 7 groups.
**Source:** `packages/kailash-ml/src/kailash_ml/__init__.py` — `__all__` AST-enumerated at 51 entries, includes `MultiModelAdapter`, `UMAPTrainable`, `HDBSCANTrainable`, `erase_subject` — none in §15.9.
**Disposition:** FILE-ISSUE. Decide per-symbol: (a) update §15.9 to canonicalize them, OR (b) demote them out of `__all__`. `MultiModelAdapter` is documented in `ml-serving.md` §2.6.1 as a 1.5.x back-compat shim and likely belongs in `__all__`; `erase_subject` is referenced in `specs-authority.md` Rule 5b evidence but not in §15.9 itself; `UMAPTrainable`/`HDBSCANTrainable` are in `engines/dim_reduction.py` and `trainable.py` but undocumented. Per `specs-authority.md` Rule 6, silent deviation between `__all__` and §15.9 is BLOCKED.
**Evidence:** `ast.parse(__init__.py)::__all__` has 51 entries; `grep -c "MultiModelAdapter\|UMAPTrainable\|HDBSCANTrainable\|erase_subject" specs/ml-engines-v2.md` = 0.
**Why this matters:** §15.9 declares ordering "load-bearing — Sphinx autodoc emits the public surface in that sequence." Any drift between `__all__` and §15.9 propagates to docs.

### [HIGH] [ml] ModelRegistry missing four spec-promised methods

**Spec:** `specs/ml-registry.md` §7 (lines 717-841) declares `promote_model`, `demote_model`, `get_model`, `list_models`, `search_models`, `diff_versions`, `list_golden_references`.
**Source:** `packages/kailash-ml/src/kailash_ml/engines/model_registry.py` — `dir(ModelRegistry)` shows `register_model`, `get_model`, `get_model_versions`, `list_models`, `promote_model`, `record_lineage`, `load_artifact`, `compare`, `import_mlflow`, `export_mlflow`, `build_lineage_graph`. Missing: `demote_model`, `search_models`, `diff_versions`, `list_golden_references`.
**Disposition:** FILE-ISSUE. Spec's `compare(name, version_a, version_b)` likely subsumes `diff_versions`; rename or document the equivalence. `demote_model` / `search_models` / `list_golden_references` look unimplemented.
**Evidence:** `getattr(ModelRegistry, 'demote_model', None)` → None; same for `search_models`, `diff_versions`, `list_golden_references`.
**Why this matters:** `facade-manager-detection.md` Rule 1: every `*Manager`/`*Registry` exposed via facade has a Tier 2 wiring test exercising its public methods. Spec-promised-but-missing methods cannot be tested.

### [HIGH] [ml] kailash_ml.rl missing many spec-promised module-level symbols

**Spec:** `specs/ml-rl-core.md` lines 214, 269, 276, 280, 307, 330, 389, 481-625 declare `EnvironmentProtocol`, `PolicyProtocol`, `ValueProtocol`, `QFunctionProtocol`, `RolloutBuffer`, `ReplayBuffer`, `OfflineDataset`, `DiagnosticReport`, plus module-level functions `record_episode`, `record_step`, `record_rollout_batch`, `record_replay_batch`, `record_policy_update`, `track_exploration`, `record_value_update`, `record_q_update`, `record_eval_rollout`.
**Source:** `packages/kailash-ml/src/kailash_ml/rl/__init__.py` — `dir(kailash_ml.rl)` returns `['EnvironmentRegistry', 'EnvironmentSpec', 'EpisodeRecord', 'EvalRecord', 'FeatureNotAvailableError', 'PolicyArtifactRef', 'PolicyRegistry', 'PolicySpec', 'PolicyVersion', 'RLLifecycleProtocol', 'RLLineage', 'RLTrainer', 'RLTrainingConfig', 'RLTrainingResult', 'TrajectorySchema', ...]`. None of the spec-promised Protocol/Buffer/Dataset classes or module-level `record_*` functions are present.
**Disposition:** FILE-ISSUE. Some `record_*` functions exist as methods on `RLDiagnostics` (`/diagnostics/rl.py:284`); spec declares them as module-level. Either lift them to module scope (matches spec), OR update spec to reference them as `RLDiagnostics.record_episode(...)`.
**Evidence:** `from kailash_ml.rl import EnvironmentProtocol, PolicyProtocol, RolloutBuffer, ReplayBuffer, OfflineDataset, DiagnosticReport` → ImportError. `from kailash_ml.rl import record_episode` → ImportError.
**Why this matters:** Spec is hundreds of lines describing a surface that has never shipped. Users copying spec code will hit ImportError on every import.

### [HIGH] [ml] MultiModelAdapter advertised in spec but absent from kailash_ml.serving.**all**

**Spec:** `specs/ml-serving.md` §2.6.1 (line 272) declares `MultiModelAdapter` as the 1.6.0 back-compat shim, importable from `kailash_ml.serving`.
**Source:** `packages/kailash-ml/src/kailash_ml/serving/__init__.py` — `dir(kailash_ml.serving)` returns `['ALLOWED_CHANNELS', 'ALLOWED_RUNTIMES', 'DEFAULT_CHANNELS', 'InferenceServer', 'InferenceServerConfig', 'InferenceServerProtocol', 'ServeHandle', 'ServeStatus', ...]` — NO `MultiModelAdapter`. (Class exists at `kailash_ml.serving.multi_model_adapter.MultiModelAdapter` and at top-level `kailash_ml.MultiModelAdapter`.)
**Disposition:** FIX-NOW (re-export from `kailash_ml.serving.__init__.py`). Spec snippets show `from kailash_ml.serving import MultiModelAdapter`.
**Evidence:** `from kailash_ml.serving import MultiModelAdapter` → ImportError. `dir(kailash_ml.serving)` does not include it.
**Why this matters:** This is the documented 1.5.0→1.6.0 hard-break recovery path; users following the migration guide hit ImportError. Same `orphan-detection.md` Rule 6 failure.

### [MED] [pact] GovernanceEngine documented `evaluate`/`can_access`/`assign_role`/`reassign` not exposed

**Spec:** `specs/pact-addressing.md` §3 GovernanceEngine — implies broad Decision API. Sample assertion: spec lists `verify_action`, `check_access`, `compute_envelope`, `get_context` (these EXIST). Some other names like `evaluate` / `can_access` / `assign_role` / `reassign` were inferred from common governance vocabulary; spec's actual list (§3.4 Mutation API) has 12 items, ALL present in code.
**Source:** Code has all of `verify_action`, `check_access`, `compute_envelope`, `get_context`, `set_role_envelope`, `set_task_envelope`, `grant_clearance`, `revoke_clearance`, `transition_clearance`, `create_bridge`, `approve_bridge`, `consent_bridge`, `reject_bridge`, `create_ksp`, `designate_acting_occupant`, `register_compliance_role`.
**Disposition:** FALSE-POSITIVE for missing methods (full mutation API matches spec). However: `pact-enforcement.md` §15.2 references `PactEngine.submit()` events — `pact.engine.PactEngine` and `pact.GovernanceEngine` are different classes with separate APIs. Spec consistency: PACT distinguishes them but a casual reader might conflate.
**Evidence:** `dir(GovernanceEngine)` and `dir(PactEngine)` show distinct method sets; both classes are top-level exported.
**Why this matters:** Minor disambiguation; spec explicitly references both classes by name. No drift, but watch for future confusion.

### [MED] [dataflow] DataFlow constructor has undocumented `runtime` parameter

**Spec:** `specs/dataflow-core.md` §1.2 lists 39 parameters explicitly. No `runtime` parameter.
**Source:** `inspect.signature(DataFlow.__init__)` reveals 40 named parameters; `runtime` is the 39th, not in spec.
**Disposition:** FIX-NOW (spec edit). Add `runtime` row to constructor table (mirrors Nexus's documented `runtime` parameter — likely the same shared-runtime pattern). Per `specs-authority.md` Rule 6, undocumented public-surface kwargs are silent deviations.
**Evidence:** `list(inspect.signature(DataFlow.__init__).parameters.keys())` includes `'runtime'` after `trust_audit_verify_key`.
**Why this matters:** `runtime` is critical for shared-runtime deployments (Nexus + DataFlow). Users who don't read source won't discover it.

### [MED] [mcp] MCPServer: spec §240 mentions `add_tool`/`add_resource`/`add_prompt`, code only has `tool`/`resource`/`prompt`

**Spec:** `specs/mcp-server.md` line 240 says "Provides `add_tool()`, `add_resource(uri)`, `add_prompt(name)` decorators."
**Source:** `dir(MCPServer)` lists `tool`, `resource`, `prompt`. No `add_tool` / `add_resource` / `add_prompt`.
**Disposition:** FIX-NOW (spec edit) — code names match the FastMCP convention used in `@server.tool(...)`/`@server.resource(...)`/`@server.prompt(...)` snippets in the spec itself (lines 119, 154, 163). The §240 text is stale.
**Evidence:** `hasattr(MCPServer, 'add_tool')` → False; `hasattr(MCPServer, 'tool')` → True.
**Why this matters:** Internal spec inconsistency between examples and prose. Low severity since users follow the @-decorator examples not the prose.

### [MED] [edge] kailash.edge does not export ConsistencyManager despite spec §676 declaring it

**Spec:** `specs/edge-computing.md` §7 (line 676) declares `ConsistencyManager` as abstract base + `StrongConsistencyManager`, `EventualConsistencyManager`, `CausalConsistencyManager`, `BoundedStalenessManager` subclasses. Spec §7 is "Public Exports" but at line 7 explicitly limits `__all__` to 4 symbols (`EdgeLocation`, `EdgeDiscovery`, `EdgeSelectionStrategy`, `ComplianceRouter`).
**Source:** `kailash.edge.consistency` module contains all four classes. Not in `kailash.edge.__init__.py`.
**Disposition:** FALSE-POSITIVE. Spec line 7 explicitly says "Only four symbols are in the top-level `kailash.edge` namespace." Per spec, ConsistencyManager lives at `kailash.edge.consistency` — and it does. Internally consistent.
**Evidence:** `from kailash.edge.consistency import ConsistencyManager` → OK.
**Why this matters:** No drift, but watch when spec evolves — easy to break.

### [MED] [ml] ml-rl-core spec is the LARGEST drift surface in the audit

**Spec:** `specs/ml-rl-core.md` (~1200 lines) declares Protocol classes, Buffer classes, OfflineDataset, DiagnosticReport, and ~9 module-level `record_*` functions.
**Source:** Only `RLTrainer`, `RLTrainingResult`, `RLTrainingConfig`, `EnvironmentRegistry`, `PolicyRegistry`, related dataclasses (`PolicyVersion`, `EpisodeRecord`, etc.) ship. The Protocol layer + buffers + module-level diagnostics are absent.
**Disposition:** FILE-ISSUE — this is HIGH if RL is a load-bearing 1.x/2.x feature. Possibly the spec is forward-looking and the implementation will land later. Either declare spec aspirational + version with `(draft)` marker, OR ship the missing surface.
**Evidence:** See HIGH-RL finding above — same root cause; logged as MED here for tracking the broader spec/code gap.
**Why this matters:** Spec drift on a 1200-line spec is the highest-leverage place to have it caught. Users implementing RL pipelines copy spec types verbatim and hit ImportError on every line.

### [LOW] [ml] kailash_ml exposes EngineNotFoundError, ClearanceRequirement, MethodSignature, ParamSpec from engines.registry but they're not in **all**

**Spec:** `specs/ml-engines-v2.md` §15.9 — Group 6 lists `engine_info`, `list_engines`. Does NOT list `EngineNotFoundError`, `ClearanceRequirement`, `MethodSignature`, `ParamSpec` even though they're eagerly imported.
**Source:** `kailash_ml/__init__.py` imports `ClearanceRequirement, EngineInfo, EngineNotFoundError, MethodSignature, ParamSpec, engine_info, list_engines` from `engines.registry` — but `__all__` only includes `engine_info`, `list_engines`. Per `orphan-detection.md` Rule 6, eagerly-imported public symbols MUST appear in `__all__`.
**Disposition:** FILE-ISSUE — either add these to `__all__` Group 6, OR demote to `_`-prefixed private imports.
**Evidence:** `kailash_ml.EngineNotFoundError` works at attribute-level but `from kailash_ml import *` skips it.
**Why this matters:** Same violation pattern as PR #523/#529 (DeviceReport `__all__` gap). Static analyzers + `from pkg import *` will silently drop these.

### [LOW] [pact] pact-enforcement spec has not been deeply audited

**Spec:** `specs/pact-enforcement.md` covers Audit Chain, Cost Tracker, Events, MCP Governance, Stores. Sampled top sections; full method-by-method audit not performed in this sweep.
**Disposition:** DEFER — re-audit in next sweep. Spot-checks confirmed `verify_audit_chain`, `envelope_snapshot`, `iter_audit_anchors`, `submit`, `submit_sync` all exist on `PactEngine`. `consumption_report` exists on `pact.costs`. Not exhaustive.
**Evidence:** Surface inspection only; full method enumeration not done.
**Why this matters:** Future sweeps should drill into McpGovernanceEnforcer, McpToolPolicy, TieredAuditDispatcher.

### [LOW] [security-data, security-threats] not audited

**Spec:** Two spec files exist (`security-data.md`, `security-threats.md`) — not opened in this sweep.
**Disposition:** DEFER — surfaces overlap with `security-auth.md` (sampled) and `dataflow-core.md` security parameters (sampled). Re-audit in next sweep.
**Why this matters:** Security-spec drift is highest-impact failure mode.

### [LOW] [scheduling, task-tracking, middleware, visualization] sampled top-of-spec only

**Spec:** Top-level imports verified; methods sampled. Full spec-vs-code method-table audit not performed.
**Disposition:** DEFER — schedules confirmed (`schedule_cron`, `schedule_interval`, `schedule_once`, `cancel`, `list_schedules` all match spec). Visualization confirmed (`WorkflowVisualizer` exported from `kailash`). Middleware top-level imports OK (`AgentUIMiddleware`, `RealtimeMiddleware`).
**Why this matters:** Lower-priority specs but still part of public contract.

## Domains audited

| Domain                                   | Specs                                                                                                                | Findings           | Notes                                                                                                                       |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------- | ------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| core                                     | core-runtime, core-nodes (top), core-workflows (top)                                                                 | 0 HIGH             | LocalRuntime/AsyncLocalRuntime/DistributedRuntime signatures match spec.                                                    |
| dataflow                                 | dataflow-core, dataflow-express                                                                                      | 1 MED              | Express CRUD signatures match. `runtime` kwarg undocumented.                                                                |
| nexus                                    | nexus-core (constructor)                                                                                             | 0                  | Constructor + 22 params match spec exactly.                                                                                 |
| kaizen                                   | kaizen-core, kaizen-llm-deployments, kaizen-evaluation, kaizen-judges, kaizen-interpretability, kaizen-observability | 3 HIGH             | Major LlmClient/LlmDeployment drift; BaseAgent re-export gap.                                                               |
| ml                                       | ml-engines-v2, ml-tracking, ml-registry, ml-serving, ml-feature-store, ml-drift, ml-rl-core                          | 4 HIGH 1 MED 1 LOW | ml-rl-core is largest single drift surface; ml-registry missing 4 methods; `__all__` includes 2 undocumented + 2 spec-only. |
| align                                    | align-ml-integration (sampled)                                                                                       | 0                  | `kailash_align.__all__` matches sampled symbols.                                                                            |
| pact                                     | pact-addressing, pact-envelopes, pact-enforcement (top), pact-absorb-capabilities                                    | 0 HIGH 1 MED       | GovernanceEngine API matches spec exactly; PactEngine absorb capabilities present.                                          |
| trust                                    | trust-eatp (sampled), trust-posture, trust-crypto (top)                                                              | 0                  | BudgetTracker, PostureStateMachine, PostureStore all match.                                                                 |
| infra                                    | infra-sql, infra-stores                                                                                              | 0                  | Dialect + DBCheckpointStore + DBEventStoreBackend all match.                                                                |
| mcp                                      | mcp-server, mcp-client (sampled), mcp-auth (sampled)                                                                 | 1 MED              | `tool/resource/prompt` work; spec line 240 prose drift.                                                                     |
| security                                 | security-auth (RBACManager)                                                                                          | 0                  | RBACManager at `kailash.trust.auth.rbac`; matches spec.                                                                     |
| edge                                     | edge-computing                                                                                                       | 0                  | Spec accurately limits `kailash.edge.__all__` to 4.                                                                         |
| scheduling                               | scheduling                                                                                                           | 0                  | All 5 documented methods present.                                                                                           |
| middleware, visualization, task-tracking | (sampled)                                                                                                            | 0 LOW              | Top-level imports verified.                                                                                                 |
| diagnostics-catalog                      | diagnostics-catalog                                                                                                  | 0                  | Protocol classes import OK.                                                                                                 |

## Domains NOT audited (and why)

- **alignment-training, alignment-serving, alignment-diagnostics**: Not opened. Align is post-Phase-F (kailash-align 0.4.x is stable); deferred to next sweep.
- **dataflow-models, dataflow-cache, dataflow-ml-integration**: Not opened. Sampled `dataflow-core` and `dataflow-express`; deeper audit deferred.
- **kaizen-signatures, kaizen-providers, kaizen-advanced, kaizen-agents-core, kaizen-agents-patterns, kaizen-agents-governance**: Not opened. Sampled `kaizen-core` and `kaizen-llm-deployments`; major drift already surfaced.
- **mcp-client, mcp-auth**: Top-level imports verified only.
- **node-catalog**: 138-node enumeration deferred — would need full Node-class introspection (separate sweep budget).
- **ml-engines-v2-addendum, ml-backends, ml-diagnostics, ml-autolog, ml-automl, ml-feature-store** (deep): Top-level checked; deep methods deferred.
- **kaizen-ml-integration, dataflow-ml-integration, nexus-ml-integration, pact-ml-integration, kailash-core-ml-integration**: Cross-framework specs — sample one (`align-ml-integration` Trainable export verified through `kailash_align.__all__`); rest deferred.
- **spec-drift-gate.md**: Tooling spec, not domain truth.
- **ml-integration.md (legacy)**: Marked DEPRECATED in `_index.md`; intentionally not audited.

## Recommended next session scope

Ranked by impact:

1. **Resolve HIGH-1 (kaizen-llm-deployments)**. Either implement `LlmClient.complete`/`stream_completion` or update spec to match `embed`/`from_deployment` surface. This is the most user-visible drift.
2. **Resolve HIGH-2 (`kaizen.core` re-exports)**. One-line fix in `kaizen/core/__init__.py` to re-export `BaseAgent`, `Signature`, `InputField`, `OutputField`. Also fixes the `rules/patterns.md` Quick Start that crashes on every fresh install.
3. **Resolve HIGH on ml-engines-v2 §15.9 vs `__all__`**. Decide canonical list: `MultiModelAdapter`, `UMAPTrainable`, `HDBSCANTrainable`, `erase_subject` either documented or demoted. Same exercise for `EngineNotFoundError`, `ClearanceRequirement`, `MethodSignature`, `ParamSpec` (LOW finding).
4. **Audit ml-rl-core deeply**. Either implement the missing Protocol/Buffer/Dataset/record\_\* surface, or mark spec `(draft)` and split out the unimplemented sections. 1200 lines of spec with ~30% missing implementation is high-leverage.
5. **Audit ml-registry deeply**. `demote_model`, `search_models`, `diff_versions`, `list_golden_references` missing or renamed. Document the `compare`/`diff_versions` equivalence.
6. **Audit alignment-training and alignment-serving**. Highest unsampled domain by spec size.
7. **Audit node-catalog**. 138-node enumeration is non-trivial but high-leverage — every node param/output is a public contract.
