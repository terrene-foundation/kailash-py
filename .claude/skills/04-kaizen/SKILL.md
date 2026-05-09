---
name: kaizen
description: "Kaizen AI agents — BaseAgent, Signature, Delegate, multi-agent, RAG, trust, governance."
---

# Kailash Kaizen — AI Agent Framework

Kaizen is a production-ready AI agent framework built on Kailash Core SDK. It provides signature-based programming, multi-agent coordination, autonomy infrastructure, and enterprise features (trust, governance, observability, cost tracking).

## When to Use

Use Kaizen when asking about AI agents, agent framework, BaseAgent, multi-agent systems, agent coordination, signatures, RAG agents, vision agents, audio agents, multimodal agents, prompt optimization, chain of thought, ReAct pattern, Planning agent, PEV, Tree-of-Thoughts, pipeline patterns (supervisor-worker, router, ensemble, blackboard, parallel, sequential, handoff, consensus, debate), A2A protocol, streaming agents, agent testing, agent memory, agentic workflows, AgentRegistry, 100+ agents, capability discovery, fault tolerance, health monitoring, trust protocol, EATP, TrustedAgent, trust chains, secure messaging, credential rotation, cross-organization agents, agent manifest, TOML manifest, GovernanceManifest, deploy agent, FileRegistry, DAG validation, schema compatibility, cost estimation, composition validation, catalog server, budget tracking, BudgetTracker, posture budget, L3 autonomy, L3 primitives (EnvelopeTracker, EnvelopeSplitter, EnvelopeEnforcer, ScopedContext, ContextScope, ScopeProjection, DataClassification, MessageRouter, MessageChannel, DeadLetterStore, AgentFactory, AgentInstance, AgentInstanceRegistry, AgentSpec, PlanExecutor, PlanValidator, PlanModification, Plan DAG), gradient zone, agent spawning, cascade termination, L3Runtime, L3EventBus, L3EventType, EatpTranslator, governance events, GovernedSupervisor, governed agent, progressive disclosure, AccountabilityTracker, CascadeManager, ClearanceEnforcer, DerelictionDetector, BypassManager, VacancyManager, kaizen-agents, PACT governance, anti-self-modification, ReadOnlyView, NaN defense, bounded collections, Delegate, delegate facade, typed events (TextDelta, ToolCallStart, DelegateEvent), run_sync, multi-provider, StreamingChatAdapter, adapter registry (OpenAI, Anthropic, Google, Ollama), tool hydration, ToolHydrator, search_tools, BM25 search, incremental streaming, token streaming, wrapper composition (WrapperBase, L3GovernedAgent, MonitoredAgent, StreamingAgent, SupervisorWrapper, DuplicateWrapperError, WrapperOrderError, canonical stacking order, GovernanceRejectedError, BudgetExhaustedError, StreamEvent, run_stream), or provider protocols (StreamingProvider, ToolCallingProvider, StructuredOutputProvider, ProviderCapability, get_provider_for_model, LLMBased routing).

## Quick Start

### Basic Agent

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from dataclasses import dataclass

class SummarizeSignature(Signature):
    text: str = InputField(description="Text to summarize")
    summary: str = OutputField(description="Generated summary")

@dataclass
class SummaryConfig:
    llm_provider: str = os.environ.get("LLM_PROVIDER", "openai")
    model: str = os.environ["LLM_MODEL"]
    temperature: float = 0.7

class SummaryAgent(BaseAgent):
    def __init__(self, config: SummaryConfig):
        super().__init__(config=config, signature=SummarizeSignature())

agent = SummaryAgent(SummaryConfig())
result = agent.run(text="Long text here...")
print(result['summary'])
```

### Pipeline Patterns (Orchestration)

```python
from kaizen_agents.patterns.pipeline import Pipeline

# Ensemble: Multi-perspective collaboration
pipeline = Pipeline.ensemble(
    agents=[code_expert, data_expert, writing_expert, research_expert],
    synthesizer=synthesis_agent,
    discovery_mode="a2a",
    top_k=3,
)
result = pipeline.run(task="Analyze codebase", input="repo_path")

# Router: Intelligent LLM-based task delegation
router = Pipeline.router(
    agents=[code_agent, data_agent, writing_agent],
    routing_strategy="semantic",
)
```

See [kaizen-key-concepts](kaizen-key-concepts.md) for the 9 pipeline patterns and the 6 autonomy subsystems.

## Critical Rules

- Define signatures before implementing agents
- Extend BaseAgent for production agents
- Use type hints in signatures for validation
- Track costs in production environments
- Test agents with real infrastructure (Tier 2/3: NO mocking — `rules/testing.md`)
- Enable hooks for observability
- Use AgentRegistry for distributed coordination
- Use `response_format` for structured output (not `provider_config`)
- Set `structured_output_mode="explicit"` for new agents
- NEVER skip signature definitions
- NEVER ignore cost tracking in production
- NEVER put structured output keys in `provider_config`

## Sub-File Index

### Getting Started

| File                                                        | Purpose                                             |
| ----------------------------------------------------------- | --------------------------------------------------- |
| [kaizen-quickstart-template](kaizen-quickstart-template.md) | Quick start guide with templates                    |
| [kaizen-baseagent-quick](kaizen-baseagent-quick.md)         | BaseAgent fundamentals                              |
| [kaizen-signatures](kaizen-signatures.md)                   | Signature-based programming                         |
| [kaizen-agent-execution](kaizen-agent-execution.md)         | Agent execution patterns                            |
| [kaizen-key-concepts](kaizen-key-concepts.md)               | Deep reference: signatures, BaseAgent, 6 subsystems |
| [README](README.md)                                         | Framework overview                                  |

### LLM Wire Layer

| File                                              | Purpose                                                                                                                                                                                                                   |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [kaizen-llm-deployment](kaizen-llm-deployment.md) | `LlmClient`, four-axis `LlmDeployment`, 24 presets, `from_env()`, wire dispatch. Load first when touching `LlmDeployment`, `LlmClient.embed()`/`complete()`, `wire_protocols/*`. Spec: `specs/kaizen-llm-deployments.md`. |

### Agent Patterns

| File                                                  | Purpose                               |
| ----------------------------------------------------- | ------------------------------------- |
| [kaizen-agent-patterns](kaizen-agent-patterns.md)     | Common agent design patterns          |
| [kaizen-chain-of-thought](kaizen-chain-of-thought.md) | Chain of thought reasoning            |
| [kaizen-react-pattern](kaizen-react-pattern.md)       | ReAct (Reason + Act) pattern          |
| [kaizen-rag-agent](kaizen-rag-agent.md)               | Retrieval-Augmented Generation agents |
| [kaizen-config-patterns](kaizen-config-patterns.md)   | Agent configuration strategies        |

### Multi-Agent & Orchestration

| File                                                    | Purpose                                             |
| ------------------------------------------------------- | --------------------------------------------------- |
| [kaizen-multi-agent-setup](kaizen-multi-agent-setup.md) | Multi-agent system setup                            |
| [kaizen-supervisor-worker](kaizen-supervisor-worker.md) | Supervisor-worker coordination                      |
| [kaizen-a2a-protocol](kaizen-a2a-protocol.md)           | Agent-to-agent communication                        |
| [kaizen-shared-memory](kaizen-shared-memory.md)         | Shared memory between agents                        |
| [kaizen-agent-registry](kaizen-agent-registry.md)       | Distributed agent coordination (100+ agent systems) |
| [kaizen-orchestration](kaizen-orchestration.md)         | 9 pipeline patterns                                 |

### Multimodal Processing

| File                                                                  | Purpose                       |
| --------------------------------------------------------------------- | ----------------------------- |
| [kaizen-multimodal-orchestration](kaizen-multimodal-orchestration.md) | Multimodal coordination       |
| [kaizen-vision-processing](kaizen-vision-processing.md)               | Vision and image processing   |
| [kaizen-audio-processing](kaizen-audio-processing.md)                 | Audio processing agents       |
| [kaizen-multimodal-pitfalls](kaizen-multimodal-pitfalls.md)           | Common pitfalls and solutions |

### Advanced Features

| File                                                        | Purpose                                           |
| ----------------------------------------------------------- | ------------------------------------------------- |
| [kaizen-control-protocol](kaizen-control-protocol.md)       | Bidirectional agent ↔ client communication        |
| [kaizen-tool-calling](kaizen-tool-calling.md)               | Autonomous tool execution with approval workflows |
| [kaizen-memory-system](kaizen-memory-system.md)             | Persistent memory, learning, FAQ detection        |
| [kaizen-checkpoint-resume](kaizen-checkpoint-resume.md)     | Checkpoint & resume for long-running agents       |
| [kaizen-interrupt-mechanism](kaizen-interrupt-mechanism.md) | Graceful shutdown, Ctrl+C handling                |
| [kaizen-persistent-memory](kaizen-persistent-memory.md)     | DataFlow-backed conversation persistence          |
| [kaizen-streaming](kaizen-streaming.md)                     | Streaming agent responses                         |
| [kaizen-cost-tracking](kaizen-cost-tracking.md)             | Cost monitoring and optimization                  |
| [kaizen-ux-helpers](kaizen-ux-helpers.md)                   | UX enhancement utilities                          |

### Observability & Monitoring

| File                                                            | Purpose                                           |
| --------------------------------------------------------------- | ------------------------------------------------- |
| [kaizen-observability-hooks](kaizen-observability-hooks.md)     | Lifecycle event hooks, production security (RBAC) |
| [kaizen-observability-tracing](kaizen-observability-tracing.md) | Distributed tracing with OpenTelemetry            |
| [kaizen-observability-metrics](kaizen-observability-metrics.md) | Prometheus metrics collection                     |
| [kaizen-observability-logging](kaizen-observability-logging.md) | Structured JSON logging                           |
| [kaizen-observability-audit](kaizen-observability-audit.md)     | Compliance audit trails                           |

### Enterprise Trust & Governance

| File                                                    | Purpose                                                                                   |
| ------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| [kaizen-trust-eatp](kaizen-trust-eatp.md)               | Trust chains, TrustedAgent, secure messaging, ESA, A2A HTTP, credential rotation (v0.8.0) |
| [kaizen-agent-manifest](kaizen-agent-manifest.md)       | TOML manifest, governance metadata, deploy, FileRegistry (v1.3)                           |
| [kaizen-composition](kaizen-composition.md)             | DAG validation, schema compatibility, cost estimation (v1.3)                              |
| [kaizen-catalog-server](kaizen-catalog-server.md)       | MCP Catalog Server, 11 tools, 14 built-in agents (v1.3)                                   |
| [kaizen-budget-tracking](kaizen-budget-tracking.md)     | BudgetTracker, PostureBudgetIntegration (v1.3)                                            |
| [kaizen-agents-governance](kaizen-agents-governance.md) | GovernedSupervisor, 7 governance modules, AuditTrail (v0.1.0)                             |
| [kaizen-agents-security](kaizen-agents-security.md)     | Anti-self-modification, NaN defense, Delegate tool security                               |

### L3 Autonomy Primitives

| File                                          | Purpose                                              |
| --------------------------------------------- | ---------------------------------------------------- |
| [kaizen-l3-overview](kaizen-l3-overview.md)   | L3Runtime, 5 subsystems, L3EventBus, EatpTranslator  |
| [kaizen-l3-envelope](kaizen-l3-envelope.md)   | EnvelopeTracker/Splitter/Enforcer, gradient zones    |
| [kaizen-l3-context](kaizen-l3-context.md)     | ContextScope, ScopeProjection, DataClassification    |
| [kaizen-l3-messaging](kaizen-l3-messaging.md) | MessageRouter, 6 typed payloads, DeadLetterStore     |
| [kaizen-l3-factory](kaizen-l3-factory.md)     | AgentFactory, 6-state lifecycle, cascade termination |
| [kaizen-l3-plan-dag](kaizen-l3-plan-dag.md)   | PlanValidator, PlanExecutor, gradient rules (G1-G8)  |

### Composition & Providers

| File                                                        | Purpose                                                                        |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------ |
| [kaizen-wrapper-composition](kaizen-wrapper-composition.md) | WrapperBase, canonical stacking, provider protocols, SPEC-02/05/10 convergence |
| [kaizen-provider-config-v25](kaizen-provider-config-v25.md) | BaseAgentConfig fields, Azure env vars, anti-patterns (v2.5.0)                 |
| [kaizen-multi-provider](kaizen-multi-provider.md)           | Provider registry, protocols, CostTracker                                      |
| [kaizen-delegate](kaizen-delegate.md)                       | Delegate facade (SPEC-05)                                                      |
| [kaizen-structured-outputs](kaizen-structured-outputs.md)   | Structured output guide with migration examples                                |

### Testing & Quality

| File                                                  | Purpose                                    |
| ----------------------------------------------------- | ------------------------------------------ |
| [kaizen-testing-patterns](kaizen-testing-patterns.md) | Testing AI agents with real infrastructure |

## Reference Documentation (Package Source)

For in-depth guides, see `packages/kailash-kaizen/docs/`:

- **Core Guides**: [BaseAgent Architecture](../../../packages/kailash-kaizen/docs/guides/baseagent-architecture.md), [Multi-Agent Coordination](../../../packages/kailash-kaizen/docs/guides/multi-agent-coordination.md), [Signature Programming](../../../packages/kailash-kaizen/docs/guides/signature-programming.md), [Hooks System](../../../packages/kailash-kaizen/docs/guides/hooks-system-guide.md), [Integration Patterns](../../../packages/kailash-kaizen/docs/guides/integration-patterns.md), [Meta-Controller](../../../packages/kailash-kaizen/docs/guides/meta-controller-guide.md), [Planning System](../../../packages/kailash-kaizen/docs/guides/planning-system-guide.md)
- **API Reference**: [API Reference](../../../packages/kailash-kaizen/docs/reference/api-reference.md), [Checkpoint](../../../packages/kailash-kaizen/docs/reference/checkpoint-api.md), [Coordination](../../../packages/kailash-kaizen/docs/reference/coordination-api.md), [Interrupts](../../../packages/kailash-kaizen/docs/reference/interrupts-api.md), [Memory](../../../packages/kailash-kaizen/docs/reference/memory-api.md), [Observability](../../../packages/kailash-kaizen/docs/reference/observability-api.md), [Planning Agents](../../../packages/kailash-kaizen/docs/reference/planning-agents-api.md), [Tools](../../../packages/kailash-kaizen/docs/reference/tools-api.md), [Configuration](../../../packages/kailash-kaizen/docs/reference/configuration.md), [Troubleshooting](../../../packages/kailash-kaizen/docs/reference/troubleshooting.md)
- **v1.0 Developer Guides** (in `packages/kailash-kaizen/docs/guides/`): `00-native-tools-guide.md`, `01-runtime-abstraction-guide.md`, `02-local-kaizen-adapter-guide.md`, `03-memory-provider-guide.md`, `04-multi-llm-routing-guide.md`, `05-unified-agent-api-guide.md`, `06-specialist-system-guide.md`, `07-task-skill-tools-guide.md`, `08-claude-code-parity-tools-guide.md`, `09-performance-optimization-guide.md`

## Integration Patterns

### With DataFlow

```python
from kaizen.core.base_agent import BaseAgent
from dataflow import DataFlow

class DataAgent(BaseAgent):
    def __init__(self, config, db: DataFlow):
        self.db = db
        super().__init__(config=config, signature=MySignature())
```

### With Nexus

```python
from kaizen.core.base_agent import BaseAgent
from nexus import Nexus

agent_workflow = create_agent_workflow()
app = Nexus()
app.register("agent", agent_workflow.build())
app.start()  # Agents available via API/CLI/MCP
```

### With Core SDK

```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("KaizenAgent", "agent1", {"agent": my_agent, "input": "..."})
```

## Related Skills

- [01-core-sdk](../01-core-sdk/SKILL.md) — Core workflow patterns
- [02-dataflow](../02-dataflow/SKILL.md) — Database integration
- [03-nexus](../03-nexus/SKILL.md) — Multi-channel deployment
- [05-kailash-mcp](../05-kailash-mcp/SKILL.md) — MCP server integration
- [17-gold-standards](../17-gold-standards/SKILL.md) — Best practices

## Support

- `kaizen-specialist` — Kaizen framework implementation
- `testing-specialist` — Agent testing strategies
- `decide-framework` skill — When to use Kaizen vs other frameworks
