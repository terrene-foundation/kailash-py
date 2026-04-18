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

| File                                                   | Description                                                                                                                                                     |
| ------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [kaizen-core.md](kaizen-core.md)                       | BaseAgent, BaseAgentConfig, AgentLoop, CoreAgent, Kaizen framework                                                                                              |
| [kaizen-signatures.md](kaizen-signatures.md)           | Signature system, InputField, OutputField, templates, structured output                                                                                         |
| [kaizen-providers.md](kaizen-providers.md)             | Provider system, execution strategies, tool integration (MCP), memory                                                                                           |
| [kaizen-advanced.md](kaizen-advanced.md)               | Composition, optimization, cost tracking, audio, A2A protocol, configuration                                                                                    |
| [kaizen-llm-deployments.md](kaizen-llm-deployments.md) | LlmClient + LlmDeployment four-axis abstraction (#498): 24 presets, auth strategies, URI/selector/legacy env resolution, §6 security contract, cross-SDK parity |

## Kaizen Agents (Layer 2 Patterns)

| File                                                       | Description                                                           |
| ---------------------------------------------------------- | --------------------------------------------------------------------- |
| [kaizen-agents-core.md](kaizen-agents-core.md)             | Delegate, AgentLoop, streaming adapter, wrapper stack                 |
| [kaizen-agents-patterns.md](kaizen-agents-patterns.md)     | Specialized agents (ReAct/CoT/ToT/Vision/Audio), multi-agent patterns |
| [kaizen-agents-governance.md](kaizen-agents-governance.md) | GovernedSupervisor, PACT integration, audit, journey orchestration    |

## PACT (Governance)

| File                                       | Description                                                              |
| ------------------------------------------ | ------------------------------------------------------------------------ |
| [pact-addressing.md](pact-addressing.md)   | D/T/R addressing grammar, organization compilation, GovernanceEngine     |
| [pact-envelopes.md](pact-envelopes.md)     | Operating envelopes (5 dimensions), clearance, 5-step access enforcement |
| [pact-enforcement.md](pact-enforcement.md) | Audit chain, budget, events, work tracking, MCP governance, stores       |

## Trust Plane (EATP)

| File                                 | Description                                                                          |
| ------------------------------------ | ------------------------------------------------------------------------------------ |
| [trust-eatp.md](trust-eatp.md)       | EATP protocol, trust chains, constraint envelope, capability attestation, delegation |
| [trust-posture.md](trust-posture.md) | TrustPosture state machine, BudgetTracker, PostureStore, audit store                 |
| [trust-crypto.md](trust-crypto.md)   | Ed25519 signing, AES-256-GCM, key management, store backends, RBAC, interop          |

## ML Lifecycle (2.0 — clean-sheet contracts)

| File                                   | Description                                                                                                                           |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| [ml-engines.md](ml-engines.md)         | **MLEngine single-point Engine contract**, `Trainable` protocol, `TrainingResult`, multi-tenancy, ONNX-default, migration shim (v2.0) |
| [ml-backends.md](ml-backends.md)       | **6 first-class backends** (cpu/cuda/mps/rocm/xpu/tpu), `detect_backend()`, precision auto, Lightning integration, hardware-gated CI  |
| [ml-tracking.md](ml-tracking.md)       | **ExperimentTracker/ModelRegistry/ArtifactStore** (MLflow-replacement), async-context, MCP surface, GDPR erasure, MLflow import       |
| [ml-integration.md](ml-integration.md) | (DEPRECATED — superseded by ml-engines/backends/tracking trio above; retained for 1.x legacy-namespace reference until 3.0 cut)       |

## Alignment (LLM Fine-Tuning)

| File                                           | Description                                                                  |
| ---------------------------------------------- | ---------------------------------------------------------------------------- |
| [alignment-training.md](alignment-training.md) | AlignmentPipeline, training methods (SFT/DPO/KTO/ORPO/GRPO/RLOO), rewards    |
| [alignment-serving.md](alignment-serving.md)   | Adapter merging, model serving (GGUF/Ollama/vLLM), evaluation, Kaizen bridge |

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
