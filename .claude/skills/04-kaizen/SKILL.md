---
name: kaizen
description: "Kailash Kaizen - production-ready AI agent framework with signature-based programming, multi-agent coordination, and enterprise features. Use when asking about 'AI agents', 'agent framework', 'BaseAgent', 'multi-agent systems', 'agent coordination', 'signatures', 'agent signatures', 'RAG agents', 'vision agents', 'audio agents', 'multimodal agents', 'agent prompts', 'prompt optimization', 'chain of thought', 'ReAct pattern', 'Planning agent', 'PEV agent', 'Tree-of-Thoughts', 'pipeline patterns', 'supervisor-worker', 'router pattern', 'ensemble pattern', 'blackboard pattern', 'parallel execution', 'agent-to-agent communication', 'A2A protocol', 'streaming agents', 'agent testing', 'agent memory', 'agentic workflows', 'AgentRegistry', 'OrchestrationRuntime', 'distributed agents', 'agent registry', '100+ agents', 'capability discovery', 'fault tolerance', 'health monitoring', 'trust protocol', 'EATP', 'TrustedAgent', 'trust chains', 'secure messaging', 'enterprise trust', 'credential rotation', 'trust verification', 'cross-organization agents', 'agent manifest', 'TOML manifest', 'GovernanceManifest', 'deploy agent', 'FileRegistry', 'introspect agent', 'DAG validation', 'validate_dag', 'schema compatibility', 'cost estimation', 'composition validation', 'catalog server', 'CatalogMCPServer', 'MCP catalog', 'budget tracking', 'BudgetTracker', 'PostureBudgetIntegration', 'posture budget', 'budget threshold', 'L3 autonomy', 'L3 primitives', 'EnvelopeTracker', 'EnvelopeSplitter', 'EnvelopeEnforcer', 'ScopedContext', 'ContextScope', 'ScopeProjection', 'DataClassification', 'MessageRouter', 'MessageChannel', 'DeadLetterStore', 'AgentFactory', 'AgentInstance', 'AgentInstanceRegistry', 'AgentSpec', 'PlanExecutor', 'PlanValidator', 'PlanModification', 'Plan DAG', 'gradient zone', 'agent spawning', 'cascade termination', 'scoped context', 'envelope enforcement', 'plan execution', or 'agent lifecycle'. Also covers L3 integration: 'L3Runtime', 'L3EventBus', 'L3EventType', 'EatpTranslator', 'L3 event system', 'EATP audit events', or 'governance events'. Also covers kaizen-agents governance layer: 'GovernedSupervisor', 'governed agent', 'progressive disclosure', 'governance modules', 'AccountabilityTracker', 'CascadeManager', 'ClearanceEnforcer', 'DerelictionDetector', 'BypassManager', 'VacancyManager', 'kaizen-agents', 'governed multi-agent', 'PACT governance', 'anti-self-modification', 'ReadOnlyView', 'governance security', 'NaN defense', or 'bounded collections'. Also covers kaizen-agents Delegate system: 'Delegate', 'delegate facade', 'typed events', 'TextDelta', 'ToolCallStart', 'DelegateEvent', 'progressive disclosure API', 'run_sync', 'budget tracking', 'multi-provider', 'StreamingChatAdapter', 'adapter registry', 'OpenAI adapter', 'Anthropic adapter', 'Google adapter', 'Ollama adapter', 'tool hydration', 'ToolHydrator', 'search_tools', 'BM25 search', 'incremental streaming', or 'token streaming'. Also covers wrapper composition: 'WrapperBase', 'wrapper stack', 'L3GovernedAgent', 'MonitoredAgent', 'StreamingAgent', 'SupervisorWrapper', 'wrapper composition', 'DuplicateWrapperError', 'WrapperOrderError', 'canonical stacking order', 'GovernanceRejectedError', 'BudgetExhaustedError', 'StreamEvent', 'run_stream', 'StreamingProvider', 'ToolCallingProvider', 'StructuredOutputProvider', 'ProviderCapability', 'get_provider_for_model', 'LLMBased routing', or 'provider protocols'."
---

# Kailash Kaizen - AI Agent Framework

Kaizen is a production-ready AI agent framework built on Kailash Core SDK that provides signature-based programming and multi-agent coordination.

## Features

Kaizen enables building sophisticated AI agents with:

- **Signature-Based Programming**: Type-safe agent interfaces with automatic validation and optimization
- **BaseAgent Architecture**: Production-ready agent foundation with error handling, audit trails, and cost tracking
- **Multi-Agent Coordination**: Supervisor-worker, agent-to-agent protocols, hierarchical structures
- **Orchestration Patterns**: 9 composable patterns (Ensemble, Blackboard, Router, Parallel, Sequential, Supervisor-Worker, Handoff, Consensus, Debate)
- **Multimodal Processing**: Vision, audio, and text processing capabilities
- **Autonomy Infrastructure**: 6 integrated subsystems (Hooks, Checkpoint, Interrupt, Memory, Planning, Meta-Controller)
- **Distributed Coordination**: AgentRegistry for 100+ agent systems with O(1) capability discovery
- **Enterprise Features**: Cost tracking, streaming responses, automatic optimization
- **Memory System**: 3-tier hierarchical storage (Hot/Warm/Cold) with DataFlow backend
- **Security**: RBAC, process isolation, compliance controls (SOC2, GDPR, HIPAA, PCI-DSS)
- **Enterprise Agent Trust Protocol (v0.8.0)**: Cryptographic trust chains, TrustedAgent, secure messaging, credential rotation
- **Performance Optimization (v1.0)**: 7 caches with 10-100x speedup (SchemaCache, EmbeddingCache, PromptCache, etc.)
- **Specialist System (v1.0)**: Claude Code-style specialists and skills with `.kaizen/` directory
- **GPT-5 Support (v1.0)**: Automatic temperature=1.0 enforcement, 8000 max_tokens for reasoning
- **Wrapper Composition System**: Stackable cross-cutting wrappers (governance, monitoring, streaming) with enforced ordering

## Quick Start

### Basic Agent

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from dataclasses import dataclass

# Define agent signature (type-safe interface)
class SummarizeSignature(Signature):
    text: str = InputField(description="Text to summarize")
    summary: str = OutputField(description="Generated summary")

# Define configuration
@dataclass
class SummaryConfig:
    llm_provider: str = os.environ.get("LLM_PROVIDER", "openai")
    model: str = os.environ["LLM_MODEL"]
    temperature: float = 0.7

# Create agent with signature
class SummaryAgent(BaseAgent):
    def __init__(self, config: SummaryConfig):
        super().__init__(
            config=config,
            signature=SummarizeSignature()
        )

# Execute
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
    discovery_mode="a2a",  # A2A semantic matching
    top_k=3                # Select top 3 agents
)

# Execute - automatically selects best agents for task
result = pipeline.run(task="Analyze codebase", input="repo_path")

# Router: Intelligent task delegation
router = Pipeline.router(
    agents=[code_agent, data_agent, writing_agent],
    routing_strategy="semantic"  # A2A-based routing
)

# Blackboard: Iterative problem-solving
blackboard = Pipeline.blackboard(
    agents=[solver, analyzer, optimizer],
    controller=controller,
    max_iterations=10,
    discovery_mode="a2a"
)
```

## Reference Documentation

### Comprehensive Guides

For in-depth documentation, see `packages/kailash-kaizen/docs/`:

**Core Guides:**

- **[BaseAgent Architecture](../../../packages/kailash-kaizen/docs/guides/baseagent-architecture.md)** - Complete unified agent system guide
- **[Multi-Agent Coordination](../../../packages/kailash-kaizen/docs/guides/multi-agent-coordination.md)** - Google A2A protocol, 5 coordination patterns
- **[Signature Programming](../../../packages/kailash-kaizen/docs/guides/signature-programming.md)** - Complete signature system guide
- **[Hooks System Guide](../../../packages/kailash-kaizen/docs/guides/hooks-system-guide.md)** - Event-driven observability framework
- **[Integration Patterns](../../../packages/kailash-kaizen/docs/guides/integration-patterns.md)** - DataFlow, Nexus, MCP integration
- **[Meta-Controller Guide](../../../packages/kailash-kaizen/docs/guides/meta-controller-guide.md)** - Intelligent task delegation
- **[Planning System Guide](../../../packages/kailash-kaizen/docs/guides/planning-system-guide.md)** - Structured workflow orchestration

**Reference Documentation:**

- **[API Reference](../../../packages/kailash-kaizen/docs/reference/api-reference.md)** - Complete API documentation
- **[Checkpoint API](../../../packages/kailash-kaizen/docs/reference/checkpoint-api.md)** - State persistence API
- **[Coordination API](../../../packages/kailash-kaizen/docs/reference/coordination-api.md)** - Multi-agent coordination API
- **[Interrupts API](../../../packages/kailash-kaizen/docs/reference/interrupts-api.md)** - Graceful shutdown API
- **[Memory API](../../../packages/kailash-kaizen/docs/reference/memory-api.md)** - 3-tier memory system API
- **[Observability API](../../../packages/kailash-kaizen/docs/reference/observability-api.md)** - Hooks and monitoring API
- **[Planning Agents API](../../../packages/kailash-kaizen/docs/reference/planning-agents-api.md)** - Planning/PEV/ToT agents API
- **[Tools API](../../../packages/kailash-kaizen/docs/reference/tools-api.md)** - Tool calling and approval API
- **[Configuration Guide](../../../packages/kailash-kaizen/docs/reference/configuration.md)** - All configuration options
- **[Troubleshooting](../../../packages/kailash-kaizen/docs/reference/troubleshooting.md)** - Common issues and solutions

### Quick Start (Skills)

- **[kaizen-quickstart-template](kaizen-quickstart-template.md)** - Quick start guide with templates
- **[kaizen-baseagent-quick](kaizen-baseagent-quick.md)** - BaseAgent fundamentals
- **[kaizen-signatures](kaizen-signatures.md)** - Signature-based programming
- **[kaizen-agent-execution](kaizen-agent-execution.md)** - Agent execution patterns
- **[README](README.md)** - Framework overview

### LLM Wire Layer (Lower-Level)

- **[kaizen-llm-deployment](kaizen-llm-deployment.md)** - `kaizen.llm.LlmClient` + four-axis `LlmDeployment` + 24 presets + `from_env()` precedence + wire-send dispatch. **Load first when touching `LlmDeployment`, `LlmClient.embed()`/`complete()`, `wire_protocols/*`, or adding a new wire-send method.** Spec: `specs/kaizen-llm-deployments.md`.

### Agent Patterns

- **[kaizen-agent-patterns](kaizen-agent-patterns.md)** - Common agent design patterns
- **[kaizen-chain-of-thought](kaizen-chain-of-thought.md)** - Chain of thought reasoning
- **[kaizen-react-pattern](kaizen-react-pattern.md)** - ReAct (Reason + Act) pattern
- **[kaizen-rag-agent](kaizen-rag-agent.md)** - Retrieval-Augmented Generation agents
- **[kaizen-config-patterns](kaizen-config-patterns.md)** - Agent configuration strategies

### Multi-Agent Systems & Orchestration

- **[kaizen-multi-agent-setup](kaizen-multi-agent-setup.md)** - Multi-agent system setup
- **[kaizen-supervisor-worker](kaizen-supervisor-worker.md)** - Supervisor-worker coordination
- **[kaizen-a2a-protocol](kaizen-a2a-protocol.md)** - Agent-to-agent communication
- **[kaizen-shared-memory](kaizen-shared-memory.md)** - Shared memory between agents
- **[kaizen-agent-registry](kaizen-agent-registry.md)** - Distributed agent coordination for 100+ agent systems

**Pipeline Patterns** (9 Composable Patterns):

- **Ensemble**: Multi-perspective collaboration with A2A discovery + synthesis
- **Blackboard**: Controller-driven iterative problem-solving
- **Router** (Meta-Controller): Intelligent task routing via A2A matching
- **Parallel**: Concurrent execution with aggregation
- **Sequential**: Linear agent chain
- **Supervisor-Worker**: Hierarchical coordination
- **Handoff**: Agent handoff with context transfer
- **Consensus**: Voting-based decision making
- **Debate**: Adversarial deliberation

### Multimodal Processing

- **[kaizen-multimodal-orchestration](kaizen-multimodal-orchestration.md)** - Multimodal coordination
- **[kaizen-vision-processing](kaizen-vision-processing.md)** - Vision and image processing
- **[kaizen-audio-processing](kaizen-audio-processing.md)** - Audio processing agents
- **[kaizen-multimodal-pitfalls](kaizen-multimodal-pitfalls.md)** - Common pitfalls and solutions

### Advanced Features

- **[kaizen-control-protocol](kaizen-control-protocol.md)** - Bidirectional agent ↔ client communication
- **[kaizen-tool-calling](kaizen-tool-calling.md)** - Autonomous tool execution with approval workflows
- **[kaizen-memory-system](kaizen-memory-system.md)** - Persistent memory, learning, FAQ detection
- **[kaizen-checkpoint-resume](kaizen-checkpoint-resume.md)** - Checkpoint & resume for long-running agents
- **[kaizen-interrupt-mechanism](kaizen-interrupt-mechanism.md)** - Graceful shutdown, Ctrl+C handling
- **[kaizen-persistent-memory](kaizen-persistent-memory.md)** - DataFlow-backed conversation persistence
- **[kaizen-streaming](kaizen-streaming.md)** - Streaming agent responses
- **[kaizen-cost-tracking](kaizen-cost-tracking.md)** - Cost monitoring and optimization
- **[kaizen-ux-helpers](kaizen-ux-helpers.md)** - UX enhancement utilities

### Observability & Monitoring

- **[kaizen-observability-hooks](kaizen-observability-hooks.md)** - Lifecycle event hooks, production security (RBAC)
- **[kaizen-observability-tracing](kaizen-observability-tracing.md)** - Distributed tracing with OpenTelemetry
- **[kaizen-observability-metrics](kaizen-observability-metrics.md)** - Prometheus metrics collection
- **[kaizen-observability-logging](kaizen-observability-logging.md)** - Structured JSON logging
- **[kaizen-observability-audit](kaizen-observability-audit.md)** - Compliance audit trails

### Enterprise Agent Trust Protocol (v0.8.0)

- **[kaizen-trust-eatp](kaizen-trust-eatp.md)** - Complete trust infrastructure for AI agents
  - Trust lineage chains with cryptographic verification
  - TrustedAgent and TrustedSupervisorAgent with built-in trust
  - Secure messaging with HMAC authentication and replay protection
  - Trust-aware orchestration with policy enforcement
  - Enterprise System Agent (ESA) for legacy system integration
  - A2A HTTP service for cross-organization trust operations
  - Credential rotation, rate limiting, and security audit logging

### Agent Manifest & Deploy (v1.3)

- **[kaizen-agent-manifest](kaizen-agent-manifest.md)** - TOML-based agent declaration, governance metadata, and deployment
  - `AgentManifest` with `[agent]` and `[governance]` TOML sections
  - `GovernanceManifest` with risk_level, suggested_posture, budget
  - `introspect_agent()` for runtime metadata extraction (Python API only, NOT MCP)
  - `deploy()` / `deploy_local()` for local FileRegistry or remote CARE Platform
  - `FileRegistry` with atomic writes and path traversal prevention

### Composition Validation (v1.3)

- **[kaizen-composition](kaizen-composition.md)** - DAG validation, schema compatibility, cost estimation
  - `validate_dag()` with iterative DFS cycle detection (max_agents=1000)
  - `check_schema_compatibility()` with JSON Schema structural subtyping and type widening
  - `estimate_cost()` with historical data projection and confidence levels

### MCP Catalog Server (v1.3)

- **[kaizen-catalog-server](kaizen-catalog-server.md)** - Standalone MCP server for agent catalog operations
  - `CatalogMCPServer` with 11 tools: Discovery (4), Deployment (3), Application (2), Governance (2)
  - Separate from KaizenMCPServer (which handles BaseAgent tools)
  - Pre-seeds 14 built-in agents on startup
  - Entry point: `python -m kaizen.mcp.catalog_server`

### Budget Tracking & Posture Integration (v1.3)

- **[kaizen-budget-tracking](kaizen-budget-tracking.md)** - Atomic budget accounting and posture-budget governance
  - `BudgetTracker` with two-phase reserve/record, threshold callbacks, `on_record()` API
  - `PostureBudgetIntegration` links budget to posture state machine
  - Configurable thresholds: warning (80%), downgrade to SUPERVISED (95%), emergency to PSEUDO_AGENT (100%)

### L3 Autonomy Primitives

- **[kaizen-l3-overview](kaizen-l3-overview.md)** - L3 primitives overview (5 subsystems)
  - EnvelopeTracker/Splitter/Enforcer for continuous budget tracking
  - ScopedContext for hierarchical context with access control
  - MessageRouter/Channel for typed inter-agent messaging
  - AgentFactory/Registry for runtime agent spawning
  - PlanValidator/Executor for DAG task graph execution
- **[kaizen-l3-envelope](kaizen-l3-envelope.md)** - Budget tracking, splitting, and non-bypassable enforcement
  - `EnvelopeTracker` with atomic recording, child allocation, reclamation
  - `EnvelopeSplitter` for stateless ratio-based budget division
  - `EnvelopeEnforcer` middleware with gradient zones (AutoApproved/Flagged/Held/Blocked)
- **[kaizen-l3-context](kaizen-l3-context.md)** - Hierarchical scoped context with projection-based access control
  - `ContextScope` tree with parent traversal and child merge
  - `ScopeProjection` glob patterns (allow/deny with deny precedence)
  - `DataClassification` 5-level clearance filtering
- **[kaizen-l3-messaging](kaizen-l3-messaging.md)** - Typed inter-agent communication
  - `MessageRouter` with 8-step validation
  - 6 typed payloads: Delegation, Status, Clarification, Completion, Escalation, System
  - `DeadLetterStore` bounded ring buffer for undeliverable messages
- **[kaizen-l3-factory](kaizen-l3-factory.md)** - Runtime agent spawning with lifecycle tracking
  - `AgentFactory` with 8-check spawn preconditions
  - 6-state lifecycle machine (Pending/Running/Waiting/Completed/Failed/Terminated)
  - Cascade termination (leaves-first)
- **[kaizen-l3-plan-dag](kaizen-l3-plan-dag.md)** - Dynamic task graph execution
  - `PlanValidator` structural + envelope validation
  - `PlanExecutor` with gradient rules (G1-G8)
  - 7 typed modifications with batch-atomic application

### v1.0 Developer Guides

Located in the package source:

- **Performance Optimization** (`09-performance-optimization-guide.md`) - Caching (10-100x speedup), parallel execution
- **Specialist System** (`06-specialist-system-guide.md`) - Claude Code-style specialists and skills
- **Native Tool System** (`00-native-tools-guide.md`) - TAOD loop tool integration
- **Runtime Abstraction** (`01-runtime-abstraction-guide.md`) - Multi-runtime support
- **LocalKaizenAdapter** (`02-local-kaizen-adapter-guide.md`) - TAOD loop implementation
- **Memory Provider** (`03-memory-provider-guide.md`) - Memory provider interface
- **Multi-LLM Routing** (`04-multi-llm-routing-guide.md`) - Intelligent LLM selection
- **Unified Agent API** (`05-unified-agent-api-guide.md`) - Simplified 2-line agent creation
- **Task/Skill Tools** (`07-task-skill-tools-guide.md`) - Subagent spawning
- **Claude Code Parity** (`08-claude-code-parity-tools-guide.md`) - 7 parity tools

### Testing & Quality

- **[kaizen-testing-patterns](kaizen-testing-patterns.md)** - Testing AI agents
- **[Performance Benchmarks](../../../packages/kailash-kaizen/docs/benchmarks/BENCHMARK_GUIDE.md)** - Measure Kaizen performance

## Key Concepts

### Signature-Based Programming

Signatures define type-safe interfaces for agents:

- **Input**: Define expected inputs with descriptions
- **Output**: Specify output format and structure
- **Validation**: Automatic type checking and validation
- **Optimization**: Framework can optimize prompts automatically

### BaseAgent Architecture

Foundation for all Kaizen agents:

- **Error Handling**: Built-in retry logic and error recovery
- **Audit Trails**: Automatic logging of agent actions
- **Cost Tracking**: Monitor API usage and costs
- **Streaming**: Support for streaming responses
- **Memory**: State management across invocations
- **Hooks System**: Zero-code-change observability and lifecycle management

### Autonomy Infrastructure (6 Subsystems)

**1. Hooks System** - Event-driven observability framework

- Zero-code-change monitoring via lifecycle events (PRE/POST hooks)
- 6 builtin hooks: Logging, Metrics, Cost, Performance, Audit, Tracing
- Production security: RBAC, Ed25519 signatures, process isolation, rate limiting
- Performance: <0.01ms overhead (625x better than 10ms target)

**2. Checkpoint System** - Persistent state management

- Save/load/fork agent state for failure recovery
- 4 storage backends: Filesystem, Redis, PostgreSQL, S3
- Automatic compression and incremental checkpoints
- State manager with deduplication and versioning

**3. Interrupt Mechanism** - Graceful shutdown and execution control

- 3 interrupt sources: USER (Ctrl+C), SYSTEM (timeout/budget), PROGRAMMATIC (API)
- 2 shutdown modes: GRACEFUL (finish cycle + checkpoint) vs IMMEDIATE (stop now)
- Signal propagation across multi-agent hierarchies

**4. Memory System** - 3-tier hierarchical storage

- Hot tier: In-memory buffer (<1ms retrieval, last 100 messages)
- Warm tier: Database (10-50ms, agent-specific history with JSONL compression)
- Cold tier: Object storage (100ms+, long-term archival with S3/MinIO)
- DataFlow-backed with auto-persist and cross-session continuity

**5. Planning Agents** - Structured workflow orchestration

- PlanningAgent: Plan before you act (pre-execution validation)
- PEVAgent: Plan, Execute, Verify, Refine (iterative refinement)
- Tree-of-Thoughts: Explore multiple reasoning paths
- Multi-step decomposition, validation, and replanning

**6. Meta-Controller Routing** - Intelligent task delegation

- A2A-based semantic capability matching (no hardcoded if/else)
- Automatic agent discovery, ranking, and selection
- Fallback strategies and load balancing
- Integrated with Router, Ensemble, and Supervisor-Worker patterns

### AgentRegistry - Distributed Coordination

For 100+ agent distributed systems:

- O(1) capability-based discovery with semantic matching
- Event broadcasting (6 event types for cross-runtime coordination)
- Health monitoring with automatic deregistration
- Status management (ACTIVE, UNHEALTHY, DEGRADED, OFFLINE)
- Multi-runtime coordination across processes/machines

## When to Use This Skill

Use Kaizen when you need to:

- Build AI agents with type-safe interfaces
- Implement multi-agent systems with orchestration patterns
- Process multimodal inputs (vision, audio, text)
- Create RAG (Retrieval-Augmented Generation) systems
- Implement chain-of-thought reasoning
- Build supervisor-worker or ensemble architectures
- Track costs and performance of AI agents
- Add zero-code-change observability to agents
- Monitor, trace, and audit agent behavior in production
- Secure agent observability with RBAC and compliance controls
- Create production-ready agentic applications
- **Enterprise trust and accountability (v0.8.0)**:
  - Cryptographic trust chains for AI agents
  - Cross-organization agent coordination
  - Regulatory compliance with audit trails
  - Secure inter-agent communication
- **Agent manifest, deploy, and composition (v1.3)**:
  - Declare agents with TOML manifests and governance metadata
  - Deploy agents to local FileRegistry or remote CARE Platform
  - Validate composite agent DAGs for cycles
  - Check schema compatibility between connected agents
  - Estimate pipeline costs from historical data
  - Discover/deploy agents via MCP Catalog Server
  - Link budget thresholds to automatic posture transitions
- **L3 Autonomy Primitives**:
  - Agent spawning with PACT-governed lifecycle tracking
  - Continuous budget tracking with gradient zones and non-bypassable enforcement
  - Hierarchical scoped context with projection-based access control
  - Typed inter-agent messaging with 8-step routing validation
  - Dynamic task graph execution with gradient-driven failure handling

**Use Pipeline Patterns When:**

- **Ensemble**: Need diverse perspectives synthesized (code review, research)
- **Blackboard**: Iterative problem-solving (optimization, debugging)
- **Router**: Intelligent task delegation to specialists
- **Parallel**: Bulk processing or voting-based consensus
- **Sequential**: Linear workflows with dependency chains

## Integration Patterns

### With DataFlow (Data-Driven Agents)

```python
from kaizen.core.base_agent import BaseAgent
from dataflow import DataFlow

class DataAgent(BaseAgent):
    def __init__(self, config, db: DataFlow):
        self.db = db
        super().__init__(config=config, signature=MySignature())
```

### With Nexus (Multi-Channel Agents)

```python
from kaizen.core.base_agent import BaseAgent
from nexus import Nexus

# Deploy agents via API/CLI/MCP
agent_workflow = create_agent_workflow()
app = Nexus()
app.register("agent", agent_workflow.build())
app.start()  # Agents available via all channels
```

### With Core SDK (Custom Workflows)

```python
from kaizen.core.base_agent import BaseAgent
from kailash.workflow.builder import WorkflowBuilder

# Embed agents in workflows
workflow = WorkflowBuilder()
workflow.add_node("KaizenAgent", "agent1", {
    "agent": my_agent,
    "input": "..."
})
```

## Provider Configuration (v2.5.0 -- Explicit over Implicit)

As of v2.5.0, provider configuration follows an **explicit over implicit** model. Structured output config is separated from provider-specific settings.

### BaseAgentConfig Fields

| Field                    | Purpose                                                                | Example                                      |
| ------------------------ | ---------------------------------------------------------------------- | -------------------------------------------- |
| `response_format`        | Structured output config (json_schema, json_object)                    | `{"type": "json_schema", "json_schema": {}}` |
| `provider_config`        | Provider-specific operational settings only                            | `{"api_version": "2024-10-21"}`              |
| `structured_output_mode` | Controls auto-generation: `"auto"` (deprecated), `"explicit"`, `"off"` | `"explicit"`                                 |

### Quick Pattern

```python
from kaizen.core.config import BaseAgentConfig
from kaizen.core.structured_output import create_structured_output_config

# Explicit mode (recommended)
config = BaseAgentConfig(
    llm_provider="openai",
    model=os.environ["LLM_MODEL"],
    response_format=create_structured_output_config(MySignature(), strict=True),
    structured_output_mode="explicit",
)

# Azure with provider-specific settings (separate from response_format)
config = BaseAgentConfig(
    llm_provider="azure",
    model=os.environ["LLM_MODEL"],
    response_format={"type": "json_object"},
    provider_config={"api_version": "2024-10-21"},
    structured_output_mode="explicit",
)
```

### Azure Env Vars (Canonical Names)

| Canonical           | Legacy (deprecated)                                    |
| ------------------- | ------------------------------------------------------ |
| `AZURE_ENDPOINT`    | `AZURE_OPENAI_ENDPOINT`, `AZURE_AI_INFERENCE_ENDPOINT` |
| `AZURE_API_KEY`     | `AZURE_OPENAI_API_KEY`, `AZURE_AI_INFERENCE_API_KEY`   |
| `AZURE_API_VERSION` | `AZURE_OPENAI_API_VERSION`                             |

Legacy vars emit `DeprecationWarning`. Use `resolve_azure_env()` from `kaizen.nodes.ai.azure_detection` for canonical-first resolution.

### Anti-Patterns

- **Never** put structured output config in `provider_config` -- use `response_format`
- **Never** rely on auto-generated structured output without understanding it -- set `structured_output_mode="explicit"`
- **Never** use multiple env var names for the same Azure setting without deprecation
- **Never** use error-based backend switching -- detect the backend upfront or set `AZURE_BACKEND` explicitly

### Prompt Utilities

`kaizen.core.prompt_utils` is the single source of truth for signature-based prompt generation:

- `generate_prompt_from_signature(signature)` -- builds system prompt from signature fields
- `json_prompt_suffix(output_fields)` -- returns JSON format instructions for Azure `json_object` compatibility

For detailed configuration patterns, see:

- **[kaizen-config-patterns](kaizen-config-patterns.md)** -- Domain configs, auto-extraction, provider-specific patterns
- **[kaizen-structured-outputs](kaizen-structured-outputs.md)** -- Full structured output guide with migration examples

## Critical Rules

- Define signatures before implementing agents
- Extend BaseAgent for production agents
- Use type hints in signatures for validation
- Track costs in production environments
- Test agents with real infrastructure (real infrastructure recommended)
- Enable hooks for observability
- Use AgentRegistry for distributed coordination
- Use `response_format` for structured output (not `provider_config`)
- Set `structured_output_mode="explicit"` for new agents
- NEVER skip signature definitions
- NEVER ignore cost tracking in production
- NEVER put structured output keys in `provider_config`
- Avoid mocking LLM calls in integration tests (real infrastructure recommended)

### Kaizen-Agents Governance (v0.1.0)

- **[kaizen-agents-governance](kaizen-agents-governance.md)** -- GovernedSupervisor, progressive disclosure (Layer 1/2/3), 7 governance modules
  - `GovernedSupervisor` with 3-layer progressive API (2-param simple -> 8-param configured -> 9 governance subsystems)
  - `AccountabilityTracker` -- D/T/R addressing, policy source chain
  - `BudgetTracker` -- reclamation, predictive warnings, reallocation
  - `CascadeManager` -- monotonic envelope tightening, BFS termination
  - `ClearanceEnforcer` + `ClassificationAssigner` -- data classification (C0-C4), regex pre-filter
  - `DerelictionDetector` -- insufficient tightening detection
  - `BypassManager` -- time-limited emergency overrides with anti-stacking
  - `VacancyManager` -- orphan detection, grandparent auto-designation
  - `AuditTrail` -- EATP hash chain with `hmac.compare_digest()`
  - SDK integration: `EnvelopeAllocator` -> `EnvelopeSplitter`, `ScopeBridge` -> `ScopedContext`

### L3 Integration & Event System

- **[kaizen-l3-overview](kaizen-l3-overview.md)** -- L3 autonomy primitives, L3Runtime integration, EATP event system
  - `L3Runtime` convenience class wiring all 5 subsystems (Factory->Enforcer, Factory->Router, Factory->Context, Enforcer->Plan)
  - `L3EventBus` pub/sub for 15 governance event types across all primitives
  - `EatpTranslator` converts L3 events into EATP audit records with severity classification

- **[kaizen-agents-security](kaizen-agents-security.md)** -- Security patterns for governance
  - Anti-self-modification via `_ReadOnlyView` proxies
  - Pervasive NaN/Inf defense (`math.isfinite()` on all numeric paths)
  - Bounded collections, monotonic invariants, thread safety
  - Delegate tool security (mandatory BashTool gate, ExecPolicy, session sanitization)

### Wrapper Composition System

Composition wrappers add cross-cutting concerns (governance, monitoring, streaming) around a `BaseAgent` without modifying it. `WrapperBase` enforces a canonical stacking order and duplicate detection.

**Canonical stacking order** (innermost to outermost):

```
BaseAgent -> L3GovernedAgent -> MonitoredAgent -> StreamingAgent
```

`WrapperBase` rejects duplicate wrappers (`DuplicateWrapperError`) and out-of-order stacking (`WrapperOrderError`). Every wrapper proxies `get_parameters()` and `to_workflow()` to the inner agent. The `innermost` property walks the full stack to the non-wrapper agent.

**Key files:**

- `packages/kaizen-agents/src/kaizen_agents/wrapper_base.py` -- `WrapperBase` with stack ordering + duplicate detection
- `packages/kaizen-agents/src/kaizen_agents/governed_agent.py` -- `L3GovernedAgent` with `ConstraintEnvelope` enforcement (Financial, Operational, Temporal, Data Access, Communication, Posture ceiling). Rejects BEFORE LLM cost is incurred. Uses `_ProtectedInnerProxy` to block governance bypass via `.inner._inner`.
- `packages/kaizen-agents/src/kaizen_agents/monitored_agent.py` -- `MonitoredAgent` with `CostTracker`, budget enforcement via `BudgetExhaustedError`, NaN/Inf defense on budget values
- `packages/kaizen-agents/src/kaizen_agents/streaming_agent.py` -- `StreamingAgent` with `run_stream()` async iterator, typed `StreamEvent` events, buffer overflow protection, timeout enforcement. Falls back to batch when provider lacks `StreamingProvider`.
- `packages/kaizen-agents/src/kaizen_agents/events.py` -- Frozen dataclass events: `TextDelta`, `ToolCallStart`, `ToolCallEnd`, `TurnComplete`, `BudgetExhausted`, `ErrorEvent`, `StreamBufferOverflow`
- `packages/kaizen-agents/src/kaizen_agents/supervisor_wrapper.py` -- `SupervisorWrapper` for task delegation to worker pool via `LLMBased` routing

**Building a wrapper stack:**

```python
from kaizen.core.base_agent import BaseAgent
from kaizen_agents.governed_agent import L3GovernedAgent
from kaizen_agents.monitored_agent import MonitoredAgent
from kaizen_agents.streaming_agent import StreamingAgent
from kaizen_agents.events import TextDelta, TurnComplete
from kailash.trust.envelope import ConstraintEnvelope, FinancialConstraint

# Stack innermost to outermost
agent = MyAgent(config=config)
governed = L3GovernedAgent(agent, envelope=ConstraintEnvelope(
    financial=FinancialConstraint(budget_limit=10.0)
))
monitored = MonitoredAgent(governed, budget_usd=5.0)
streaming = StreamingAgent(monitored)

# Stream typed events
async for event in streaming.run_stream(prompt="analyze this"):
    match event:
        case TextDelta(text=t): print(t, end="")
        case TurnComplete(text=t): print(f"\n[Done: {t[:50]}]")
```

**SupervisorWrapper** -- delegates tasks to a worker pool using LLM-based routing:

```python
from kaizen_agents.supervisor_wrapper import SupervisorWrapper
from kaizen_agents.patterns.llm_routing import LLMBased

supervisor = SupervisorWrapper(inner_agent, workers=[w1, w2], routing=LLMBased())
result = await supervisor.run_async(task="complex task")
```

### Provider Capability Protocols

SPEC-02 defines `runtime_checkable` protocols in `kaizen.providers.base` for structural capability discovery. Providers satisfy protocols structurally -- no explicit inheritance needed.

| Protocol                   | Key Method                          | Purpose                        |
| -------------------------- | ----------------------------------- | ------------------------------ |
| `StreamingProvider`        | `stream_chat()` -> `StreamEvent`    | Token-by-token streaming       |
| `ToolCallingProvider`      | `chat_with_tools(messages, tools)`  | Native function calling        |
| `StructuredOutputProvider` | `chat_structured(messages, schema)` | JSON schema structured outputs |
| `AsyncLLMProvider`         | `chat_async(messages)`              | Async chat completions         |

`ProviderCapability` enum: `CHAT_SYNC`, `CHAT_ASYNC`, `CHAT_STREAM`, `TOOLS`, `STRUCTURED_OUTPUT`, `EMBEDDINGS`, `VISION`, `AUDIO`, `REASONING_MODELS`, `BYOK`.

Use `get_provider_for_model(model)` from `kaizen.providers.registry` to resolve a model string to a provider instance. Use `isinstance(provider, StreamingProvider)` for capability checks.

### LLM-Based Routing

`LLMBased` from `kaizen_agents.patterns.llm_routing` scores agent capabilities against task requirements using Kaizen signatures (not keyword matching or dispatch tables).

```python
from kaizen_agents.patterns.llm_routing import LLMBased

routing = LLMBased(config=config)  # config optional; falls back to .env defaults
score = await routing.score("analyze revenue data", agent_capability)
best = await routing.select_best("analyze revenue data", [agent1, agent2, agent3])
```

`score()` returns `[0.0, 1.0]`. Accepts `Capability` dataclasses (`.name` + `.description`) or plain strings. `select_best()` returns the highest-scoring candidate or `None` when empty.

### Convergence Status (SPEC-02 / SPEC-05 / SPEC-10)

Three convergence SPECs have shipped on the `feat/spec04-baseagent-slim` branch:

**SPEC-02 (Provider Split)** -- The provider monolith (`kaizen.nodes.ai.ai_providers`) is now split into per-provider modules under `kaizen/providers/`. See **[kaizen-multi-provider](kaizen-multi-provider.md)** for the updated registry, protocols, and CostTracker.

- `kaizen.providers.base` -- `ProviderCapability` enum (10 members), 5 runtime-checkable protocols
- `kaizen.providers.registry` -- `ProviderRegistry` with 14 provider entries and prefix-dispatch model detection
- `kaizen.providers.cost` -- `CostTracker` with thread-safe accumulation
- Backward-compat shim at `kaizen.nodes.ai.ai_providers` re-exports all public names

**SPEC-05 (Delegate Facade)** -- Delegate is now a composition facade wrapping `AgentLoop -> [L3GovernedAgent] -> [MonitoredAgent]`. See **[kaizen-delegate](kaizen-delegate.md)** for the updated API surface.

- `ConstructorIOError` -- raised on outbound IO in `__init__`
- `ToolRegistryCollisionError` -- raised on duplicate tool name registration
- `run_sync()` refuses under a running event loop with an actionable error message
- Deferred MCP: `mcp_servers=` stores configs, connects on first `run()`
- Introspection: `.core_agent`, `.signature`, `.model` read-only properties

**SPEC-10 (Multi-Agent)** -- 11 deprecated agent subclasses (SupervisorAgent, WorkerAgent, CoordinatorAgent, PipelineStageAgent, etc.) now emit `DeprecationWarning`. Composition patterns accept plain `BaseAgent` instances. `max_total_delegations` cap (default 20) with `DelegationCapExceeded` exception.

## Related Skills

- **[01-core-sdk](../../01-core-sdk/SKILL.md)** - Core workflow patterns
- **[02-dataflow](../dataflow/SKILL.md)** - Database integration
- **[03-nexus](../nexus/SKILL.md)** - Multi-channel deployment
- **[05-kailash-mcp](../05-kailash-mcp/SKILL.md)** - MCP server integration
- **[17-gold-standards](../../17-gold-standards/SKILL.md)** - Best practices

## Support

For Kaizen-specific questions, invoke:

- `kaizen-specialist` - Kaizen framework implementation
- `testing-specialist` - Agent testing strategies
- ``decide-framework` skill` - When to use Kaizen vs other frameworks
