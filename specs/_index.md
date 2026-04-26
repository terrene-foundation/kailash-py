# Kailash Python SDK — Specs Index

Domain truth for the Kailash platform. Each file is authoritative for its domain. When code and spec disagree, update the spec or fix the code — never leave them divergent.

## Core SDK

| File                                   | Description                                                                   |
| -------------------------------------- | ----------------------------------------------------------------------------- |
| [core-nodes.md](core-nodes.md)         | Node architecture, Node base class, NodeParameter, NodeMetadata, NodeRegistry |
| [core-workflows.md](core-workflows.md) | WorkflowBuilder, Connection, CyclicConnection, workflow validation            |
| [core-runtime.md](core-runtime.md)     | LocalRuntime, AsyncLocalRuntime, DistributedRuntime, cycles, resilience, DLQ  |
| [core-servers.md](core-servers.md)     | WorkflowServer variants, create_gateway, error/exception hierarchy            |

## DataFlow

| File                                       | Description                                                                    |
| ------------------------------------------ | ------------------------------------------------------------------------------ |
| [dataflow-core.md](dataflow-core.md)       | DataFlow class, constructor, configuration, connection URL, engine, exceptions |
| [dataflow-express.md](dataflow-express.md) | Express API (create/read/update/delete/list/count/bulk), Express Sync          |
| [dataflow-models.md](dataflow-models.md)   | @db.model, field types, validation, classification, multi-tenant               |
| [dataflow-cache.md](dataflow-cache.md)     | Cache layer, dialect, record ID coercion, transactions, pooling                |

## Nexus

| File                                   | Description                                                                  |
| -------------------------------------- | ---------------------------------------------------------------------------- |
| [nexus-core.md](nexus-core.md)         | Nexus class, NexusEngine, builder, presets, configuration                    |
| [nexus-channels.md](nexus-channels.md) | Transport system (HTTP/CLI/MCP/WebSocket/Webhook), handler registry          |
| [nexus-auth.md](nexus-auth.md)         | JWT auth, RBAC, API key, CORS, session management, tenant isolation          |
| [nexus-services.md](nexus-services.md) | Events, middleware, probes, OpenAPI, metrics, background services, discovery |

## Kaizen (AI Agent Framework)

| File                                                     | Description                                                                                                                                                                                                                                                                                 |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [kaizen-core.md](kaizen-core.md)                         | BaseAgent, BaseAgentConfig, AgentLoop, CoreAgent, Kaizen framework                                                                                                                                                                                                                          |
| [kaizen-signatures.md](kaizen-signatures.md)             | Signature system, InputField, OutputField, templates, structured output                                                                                                                                                                                                                     |
| [kaizen-providers.md](kaizen-providers.md)               | Provider system, execution strategies, tool integration (MCP), memory                                                                                                                                                                                                                       |
| [kaizen-advanced.md](kaizen-advanced.md)                 | Composition, optimization, cost tracking, audio, A2A protocol, configuration                                                                                                                                                                                                                |
| [kaizen-llm-deployments.md](kaizen-llm-deployments.md)   | LlmClient + LlmDeployment four-axis abstraction (#498): 24 presets, auth strategies, URI/selector/legacy env resolution, §6 security contract, cross-SDK parity                                                                                                                             |
| [kaizen-interpretability.md](kaizen-interpretability.md) | **InterpretabilityDiagnostics adapter** (cross-SDK Diagnostic Protocol, PR#4 of #567): attention heatmaps / logit lens / linear probes / SAE features on local open-weight LLMs, `[interpretability]` extra                                                                                 |
| [kaizen-judges.md](kaizen-judges.md)                     | **LLMDiagnostics + LLMJudge** (cross-SDK JudgeCallable + Diagnostic Protocols, PR#5 of #567): Delegate-routed LLM-as-judge with position-swap bias mitigation, microdollar budget enforcement, `[judges]` extra                                                                             |
| [kaizen-evaluation.md](kaizen-evaluation.md)             | **Algorithmic NLP metrics** (ROUGE / BLEU / BERTScore, split from `kaizen.judges` per SYNTHESIS PR#5): pure-math reference comparison, no LLM / cost / budget surface, `[evaluation]` extra                                                                                                 |
| [kaizen-observability.md](kaizen-observability.md)       | **AgentDiagnostics + TraceExporter** (cross-SDK Diagnostic + TraceEvent Protocols, PR#6 of #567): context-managed agent-run diagnostics, single-filter-point sink adapter with N4 canonical fingerprint parity (kailash-rs#468 / v3.17.1+), BaseAgent hot-path wiring, no Langfuse coupling |

## Kaizen Agents (Layer 2 Patterns)

| File                                                       | Description                                                           |
| ---------------------------------------------------------- | --------------------------------------------------------------------- |
| [kaizen-agents-core.md](kaizen-agents-core.md)             | Delegate, AgentLoop, streaming adapter, wrapper stack                 |
| [kaizen-agents-patterns.md](kaizen-agents-patterns.md)     | Specialized agents (ReAct/CoT/ToT/Vision/Audio), multi-agent patterns |
| [kaizen-agents-governance.md](kaizen-agents-governance.md) | GovernedSupervisor, PACT integration, audit, journey orchestration    |

## PACT (Governance)

| File                                                       | Description                                                                                                                                                 |
| ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [pact-addressing.md](pact-addressing.md)                   | D/T/R addressing grammar, organization compilation, GovernanceEngine                                                                                        |
| [pact-envelopes.md](pact-envelopes.md)                     | Operating envelopes (5 dimensions), clearance, 5-step access enforcement                                                                                    |
| [pact-enforcement.md](pact-enforcement.md)                 | Audit chain, budget, events, work tracking, MCP governance, stores, N4/N5 cross-SDK conformance runner                                                      |
| [pact-absorb-capabilities.md](pact-absorb-capabilities.md) | Absorbed governance-diagnostic capabilities (#567 PR#7): verify_audit_chain, envelope_snapshot, iter_audit_anchors, consumption_report, run_negative_drills |

## Trust Plane (EATP)

| File                                 | Description                                                                          |
| ------------------------------------ | ------------------------------------------------------------------------------------ |
| [trust-eatp.md](trust-eatp.md)       | EATP protocol, trust chains, constraint envelope, capability attestation, delegation |
| [trust-posture.md](trust-posture.md) | TrustPosture state machine, BudgetTracker, PostureStore, audit store                 |
| [trust-crypto.md](trust-crypto.md)   | Ed25519 signing, AES-256-GCM, key management, store backends, RBAC, interop          |

## ML Lifecycle 2.0 — Engine Core

| File                                                   | Description                                                                                                                                                                             |
| ------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [ml-engines-v2.md](ml-engines-v2.md)                   | **MLEngine single-point Engine contract (1.0.0)**, 8-method surface, `Trainable` protocol, `TrainingResult` + `DeviceReport`, `km.*` convenience wrappers, canonical README Quick Start |
| [ml-engines-v2-addendum.md](ml-engines-v2-addendum.md) | **Engine addendum**: classical-ML surface, scikit-learn / lightgbm / xgboost / catboost trainables, legacy v1 namespace migration, Pydantic-to-DataFrame adapter                        |
| [ml-backends.md](ml-backends.md)                       | **6 first-class backends** (cpu/cuda/mps/rocm/xpu/tpu), `detect_backend()`, precision auto, Lightning integration, hardware-gated CI matrix                                             |
| [ml-diagnostics.md](ml-diagnostics.md)                 | **DLDiagnostics adapter** (cross-SDK Diagnostic Protocol), torch-hook training instrumentation, plotly gated by `[dl]` extra (PR#1 of #567)                                             |

## ML Lifecycle 2.0 — Experiment, Registry, Serving

| File                             | Description                                                                                                                                                                |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [ml-tracking.md](ml-tracking.md) | **ExperimentTracker** (MLflow-replacement), async-context ambient-run scope, nested runs, auto-logging, GDPR erasure, MLflow import bridge                                 |
| [ml-registry.md](ml-registry.md) | **ModelRegistry** (staging → shadow → production → archived lifecycle), alias resolution, `ArtifactStore` abstraction (LocalFile / CAS sha256), ONNX-default serialisation |
| [ml-serving.md](ml-serving.md)   | **Inference server + ServeHandle**, REST / MCP channels, model-signature input validation, batch mode, Nexus integration, `km.serve()` dispatch                            |
| [ml-autolog.md](ml-autolog.md)   | **Auto-logging contract**: sklearn / lightgbm / PyTorch Lightning / torch training loops, ambient-run detection, metric namespace discipline, non-intrusive patching       |

## ML Lifecycle 2.0 — AutoML, Drift, Feature Store, Dashboard

| File                                       | Description                                                                                                                                                                         |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [ml-automl.md](ml-automl.md)               | **AutoMLEngine** (agent-infused with LLM guardrails), search strategies (grid / random / bayesian / successive-halving), cost budget, human-approval gate, audit trail              |
| [ml-drift.md](ml-drift.md)                 | **DriftMonitor** (KS / chi2 / PSI / Jensen-Shannon), reference-vs-current comparison, scheduled monitoring, feature-level + overall drift reports, drift-triggered retraining hooks |
| [ml-feature-store.md](ml-feature-store.md) | **FeatureStore** (polars-native, ConnectionManager-backed), point-in-time queries, schema enforcement, feature versioning, tenant-scoped keys                                       |
| [ml-dashboard.md](ml-dashboard.md)         | **MLDashboard** (`kailash-ml-dashboard` CLI + `km.dashboard()` launcher), runs / models / serving visualisation, plotly-based, notebook-friendly background-thread launch           |

## ML Lifecycle 2.0 — Reinforcement Learning

| File                                                     | Description                                                                                                                                                         |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [ml-rl-core.md](ml-rl-core.md)                           | **RL core surface**: `RLTrainer`, `EnvironmentRegistry`, `PolicyRegistry`, `km.rl_train()`, Stable-Baselines3 + Gymnasium integration, `[rl]` extra                 |
| [ml-rl-algorithms.md](ml-rl-algorithms.md)               | **RL algorithms catalog**: PPO / SAC / DQN / A2C / TD3 / DDPG baselines, MaskablePPO, Decision Transformer, hyperparameter presets, algorithm-family contracts      |
| [ml-rl-align-unification.md](ml-rl-align-unification.md) | **RL + Alignment unification**: shared trajectory schema, GRPO / RLOO / PPO-LM cross-framework interop, reward-hacking signal, kailash-align ↔ kailash-ml.rl bridge |

## ML Integrations (cross-framework supporting specs)

| File                                                             | Description                                                                                                                                     |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| [kailash-core-ml-integration.md](kailash-core-ml-integration.md) | Core SDK ↔ ML bridge: extras alias (`pip install kailash[ml]`), workflow-node adapters, `kailash.ml` namespace re-export                        |
| [dataflow-ml-integration.md](dataflow-ml-integration.md)         | DataFlow ↔ ML bridge: `TrainingContext`, `lineage_dataset_hash` provenance, multi-tenant feature-group classification, ML-event subscribers     |
| [nexus-ml-integration.md](nexus-ml-integration.md)               | Nexus ↔ ML bridge: ml-endpoints mount (REST + MCP + WS), `UserContext` preservation, channel-aware `ServeHandle`, dashboard embed               |
| [kaizen-ml-integration.md](kaizen-ml-integration.md)             | Kaizen ↔ ML bridge: §2.4 Agent Tool Discovery via `km.engine_info()`, `SQLiteSink` TraceExporter, shared `CostTracker`, `_kml_agent_*` tables   |
| [align-ml-integration.md](align-ml-integration.md)               | Align ↔ ML bridge: fine-tuning-as-training-engine, LoRA Lightning callback, RL ↔ alignment trajectory unification via `ml-rl-align-unification` |
| [pact-ml-integration.md](pact-ml-integration.md)                 | PACT ↔ ML bridge: `ml_context` envelope kwarg, D/T/R clearance on engine methods, governance-gated AutoML + registry                            |

## ML Lifecycle (Legacy)

| File                                   | Description                                                                                                                                      |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| [ml-integration.md](ml-integration.md) | (DEPRECATED — superseded by the ml-engines-v2 / ml-backends / ml-tracking trio above; retained for 1.x legacy-namespace reference until 3.0 cut) |

## Alignment (LLM Fine-Tuning)

| File                                                 | Description                                                                                                                                                  |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [alignment-training.md](alignment-training.md)       | AlignmentPipeline, training methods (SFT/DPO/KTO/ORPO/GRPO/RLOO), rewards                                                                                    |
| [alignment-serving.md](alignment-serving.md)         | Adapter merging, model serving (GGUF/Ollama/vLLM), evaluation, Kaizen bridge                                                                                 |
| [alignment-diagnostics.md](alignment-diagnostics.md) | **AlignmentDiagnostics adapter** (cross-SDK Diagnostic Protocol), KL/reward-margin/win-rate, bounded training-metric ingestion, reward-hacking signal (PR#3) |

## MCP (Model Context Protocol)

| File                           | Description                                                                       |
| ------------------------------ | --------------------------------------------------------------------------------- |
| [mcp-server.md](mcp-server.md) | MCPServer, tool/resource/prompt registration, execution pipeline, platform server |
| [mcp-client.md](mcp-client.md) | MCPClient, transport, discovery, health checks, tool hydration                    |
| [mcp-auth.md](mcp-auth.md)     | OAuth 2.1, JWT, API key, Basic auth, rate limiting, protocol, advanced features   |

## Infrastructure

| File                               | Description                                                                         |
| ---------------------------------- | ----------------------------------------------------------------------------------- |
| [infra-sql.md](infra-sql.md)       | Dialect system, portability matrix, quote_identifier, connection management         |
| [infra-stores.md](infra-stores.md) | Stores (checkpoint/event/execution/idempotency/DLQ), task queue, workers, migration |

## Security

| File                                       | Description                                                                   |
| ------------------------------------------ | ----------------------------------------------------------------------------- |
| [security-auth.md](security-auth.md)       | JWT subsystems, API key, SSO, MFA, RBAC, ABAC, sessions                       |
| [security-data.md](security-data.md)       | Secrets management, credential handling, encryption, DataFlow access controls |
| [security-threats.md](security-threats.md) | Threat model, audit logging, exception hierarchy, configuration defaults      |

## Runtime Extensions

| File                                   | Description                                                                    |
| -------------------------------------- | ------------------------------------------------------------------------------ |
| [scheduling.md](scheduling.md)         | WorkflowScheduler, cron/interval/one-shot scheduling, SQLite job store         |
| [task-tracking.md](task-tracking.md)   | TaskManager, MetricsCollector, TaskStatus state machine, storage backends      |
| [edge-computing.md](edge-computing.md) | EdgeDiscovery, ComplianceRouter, ConsistencyManager, edge coordination         |
| [middleware.md](middleware.md)         | AgentUIMiddleware, APIGateway, RealtimeMiddleware, auth/comm/DB/MCP middleware |
| [visualization.md](visualization.md)   | WorkflowVisualizer, PerformanceVisualizer, dashboards, Mermaid diagrams        |

## Reference

| File                               | Description                                                         |
| ---------------------------------- | ------------------------------------------------------------------- |
| [node-catalog.md](node-catalog.md) | All 138 nodes by category with parameters, outputs, and constraints |

## Tooling & Quality

| File                                     | Description                                                                                                                                 |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| [spec-drift-gate.md](spec-drift-gate.md) | Mechanical pre-commit + CI check that verifies spec assertions against code; section-context inference, override directives, baseline grace |
