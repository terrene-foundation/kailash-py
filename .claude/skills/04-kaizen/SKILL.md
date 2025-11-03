---
name: kaizen
description: "Kailash Kaizen - production-ready AI agent framework with signature-based programming, multi-agent coordination, and enterprise features. Use when asking about 'AI agents', 'agent framework', 'BaseAgent', 'multi-agent systems', 'agent coordination', 'signatures', 'agent signatures', 'RAG agents', 'vision agents', 'audio agents', 'multimodal agents', 'agent prompts', 'prompt optimization', 'chain of thought', 'ReAct pattern', 'Planning agent', 'PEV agent', 'Tree-of-Thoughts', 'pipeline patterns', 'supervisor-worker', 'router pattern', 'ensemble pattern', 'blackboard pattern', 'parallel execution', 'agent-to-agent communication', 'A2A protocol', 'streaming agents', 'agent testing', 'agent memory', or 'agentic workflows'."
---

# Kailash Kaizen - AI Agent Framework

Kaizen is a production-ready AI agent framework built on Kailash Core SDK that provides signature-based programming and multi-agent coordination.

## 🆕 v0.6.0 Highlights

**Enhanced Autonomy & Memory Systems** (Released 2025-10-29):

- **Interrupt Mechanism**: Complete graceful shutdown with Ctrl+C handling, timeout/budget auto-stop, checkpoint preservation
  - 3 interrupt sources (USER, SYSTEM, PROGRAMMATIC)
  - 2 shutdown modes (GRACEFUL, IMMEDIATE)
  - Signal propagation across multi-agent systems
  - 34 E2E tests production-validated

- **Persistent Buffer Memory**: DataFlow-backed conversation persistence with dual-buffer architecture
  - In-memory buffer + database storage
  - Auto-persist (configurable intervals)
  - JSONL compression (60%+ reduction)
  - Cross-session persistence
  - 28 E2E tests with real database

- **Enhanced Hooks**: PRE/POST_INTERRUPT and PRE/POST_CHECKPOINT_SAVE events

See **[kaizen-interrupt-mechanism](kaizen-interrupt-mechanism.md)** and **[kaizen-persistent-memory](kaizen-persistent-memory.md)** for details.

---

## Overview

Kaizen enables building sophisticated AI agents with:

- **Signature-Based Programming**: Type-safe agent interfaces with automatic validation
- **BaseAgent Architecture**: Production-ready agent foundation with error handling
- **Multi-Agent Coordination**: Supervisor-worker, agent-to-agent protocols
- **Multimodal Processing**: Vision, audio, and text processing
- **Enterprise Features**: Cost tracking, audit trails, streaming responses
- **Automatic Optimization**: Prompt refinement and performance tuning

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
    llm_provider: str = "openai"
    model: str = "gpt-4"
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
from kaizen.orchestration.pipeline import Pipeline

# Ensemble: Multi-perspective collaboration
pipeline = Pipeline.ensemble(
    agents=[code_expert, data_expert, writing_expert, research_expert],
    synthesizer=synthesis_agent,
    discovery_mode="a2a",  # A2A semantic matching
    top_k=3                # Select top 3 agents
)

# Execute - automatically selects best agents for task
result = pipeline.run(task="Analyze codebase", input="repo_path")
print(result['result'])  # Synthesized result from multiple perspectives

# Router: Intelligent task delegation
router = Pipeline.router(
    agents=[code_agent, data_agent, writing_agent],
    routing_strategy="semantic"  # A2A-based routing
)
result = router.run(task="Analyze sales data")  # Routes to data_agent

# Blackboard: Iterative problem-solving
blackboard = Pipeline.blackboard(
    agents=[solver, analyzer, optimizer],
    controller=controller,
    max_iterations=10,
    discovery_mode="a2a"
)
result = blackboard.run(task="Optimize query", input="slow_query.sql")
```

## Reference Documentation

### Comprehensive Guides

For in-depth documentation, see `apps/kailash-kaizen/docs/`:

**Core Guides:**
- **[BaseAgent Architecture](../../../apps/kailash-kaizen/docs/guides/baseagent-architecture.md)** - Complete unified agent system guide
- **[Multi-Agent Coordination](../../../apps/kailash-kaizen/docs/guides/multi-agent-coordination.md)** - Google A2A protocol, 5 coordination patterns
- **[Signature Programming](../../../apps/kailash-kaizen/docs/guides/signature-programming.md)** - Complete signature system guide
- **[Hooks System Guide](../../../apps/kailash-kaizen/docs/guides/hooks-system-guide.md)** - Event-driven observability framework
- **[Integration Patterns](../../../apps/kailash-kaizen/docs/guides/integration-patterns.md)** - DataFlow, Nexus, MCP integration

**Reference Documentation:**
- **[API Reference](../../../apps/kailash-kaizen/docs/reference/api-reference.md)** - Complete API documentation
- **[Hooks System](../../../apps/kailash-kaizen/docs/features/hooks-system.md)** - Lifecycle event hooks reference
- **[Configuration Guide](../../../apps/kailash-kaizen/docs/reference/configuration.md)** - All configuration options
- **[Troubleshooting](../../../apps/kailash-kaizen/docs/reference/troubleshooting.md)** - Common issues and solutions

### Quick Start (Skills)
- **[kaizen-quickstart-template](kaizen-quickstart-template.md)** - Quick start guide with templates
- **[kaizen-baseagent-quick](kaizen-baseagent-quick.md)** - BaseAgent fundamentals
- **[kaizen-signatures](kaizen-signatures.md)** - Signature-based programming
- **[kaizen-agent-execution](kaizen-agent-execution.md)** - Agent execution patterns
- **[README](README.md)** - Framework overview

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

**A2A-Integrated Patterns (4)**: Ensemble, Blackboard, Router, Supervisor-Worker

### Multimodal Processing
- **[kaizen-multimodal-orchestration](kaizen-multimodal-orchestration.md)** - Multimodal coordination
- **[kaizen-vision-processing](kaizen-vision-processing.md)** - Vision and image processing
- **[kaizen-audio-processing](kaizen-audio-processing.md)** - Audio processing agents
- **[kaizen-multimodal-pitfalls](kaizen-multimodal-pitfalls.md)** - Common pitfalls and solutions

### Advanced Features
- **[kaizen-control-protocol](kaizen-control-protocol.md)** - Bidirectional agent ↔ client communication
- **[kaizen-tool-calling](kaizen-tool-calling.md)** - Autonomous tool execution with approval workflows
- **[kaizen-memory-system](kaizen-memory-system.md)** - Persistent memory, learning, FAQ detection, preference adaptation
- **[kaizen-checkpoint-resume](kaizen-checkpoint-resume.md)** - Checkpoint & resume for long-running agents, failure recovery
- **[kaizen-interrupt-mechanism](kaizen-interrupt-mechanism.md)** - 🆕 v0.6.0: Graceful shutdown, Ctrl+C handling, timeout/budget auto-stop, checkpoint preservation
- **[kaizen-persistent-memory](kaizen-persistent-memory.md)** - 🆕 v0.6.0: DataFlow-backed conversation persistence, dual-buffer architecture, auto-persist
- **[kaizen-streaming](kaizen-streaming.md)** - Streaming agent responses
- **[kaizen-cost-tracking](kaizen-cost-tracking.md)** - Cost monitoring and optimization
- **[kaizen-ux-helpers](kaizen-ux-helpers.md)** - UX enhancement utilities

### Observability & Monitoring
- **[kaizen-observability-hooks](kaizen-observability-hooks.md)** - Lifecycle event hooks, hook management, and production security (RBAC, isolation, metrics auth)
- **[kaizen-observability-tracing](kaizen-observability-tracing.md)** - Distributed tracing with OpenTelemetry and Jaeger
- **[kaizen-observability-metrics](kaizen-observability-metrics.md)** - Prometheus metrics collection with p50/p95/p99 percentiles
- **[kaizen-observability-logging](kaizen-observability-logging.md)** - Structured JSON logging for ELK Stack integration
- **[kaizen-observability-audit](kaizen-observability-audit.md)** - Compliance audit trails (SOC2, GDPR, HIPAA, PCI-DSS)

### Testing & Quality
- **[kaizen-testing-patterns](kaizen-testing-patterns.md)** - Testing AI agents

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
- See: `docs/guides/hooks-system-guide.md`

**2. Checkpoint System** - Persistent state management
- Save/load/fork agent state for failure recovery and experimentation
- 4 storage backends: Filesystem, Redis, PostgreSQL, S3
- Automatic compression and incremental checkpoints
- State manager with deduplication and versioning
- See: `docs/guides/state-persistence-guide.md`

**3. Interrupt Mechanism** - Graceful shutdown and execution control
- 3 interrupt sources: USER (Ctrl+C), SYSTEM (timeout/budget), PROGRAMMATIC (API)
- 2 shutdown modes: GRACEFUL (finish cycle + checkpoint) vs IMMEDIATE (stop now)
- Signal propagation across multi-agent hierarchies
- 34 E2E tests production-validated, examples in `examples/autonomy/interrupts/`
- See: `docs/guides/interrupt-mechanism-guide.md`

**4. Memory System** - 3-tier hierarchical storage (Hot/Warm/Cold)
- Hot tier: In-memory buffer (<1ms retrieval, last 100 messages)
- Warm tier: Database (10-50ms, agent-specific history with JSONL compression)
- Cold tier: Object storage (100ms+, long-term archival with S3/MinIO)
- DataFlow-backed with auto-persist and cross-session continuity
- 28 E2E tests with real database operations
- See: `docs/guides/memory-and-learning-system.md`

**5. Planning Agents** - Structured workflow orchestration
- PlanningAgent: Plan before you act (pre-execution validation)
- PEVAgent: Plan, Execute, Verify, Refine (iterative refinement)
- Multi-step decomposition, validation, and replanning
- Best for: Research, compliance, code generation
- See: `docs/guides/planning-agents-guide.md`

**6. Meta-Controller Routing** - Intelligent task delegation
- A2A-based semantic capability matching (no hardcoded if/else)
- Automatic agent discovery, ranking, and selection
- Fallback strategies and load balancing
- Integrated with Router, Ensemble, and Supervisor-Worker patterns
- See: `docs/guides/meta-controller-routing-guide.md`

### Hooks System (Lifecycle Events)
Event-driven framework for zero-code-change observability with production security:
- **Location**: `kaizen.core.autonomy.hooks`, `kaizen.core.autonomy.hooks.security`
- **Usage**: Register hooks on PRE/POST lifecycle events (opt-in via `config.hooks_enabled=True`)
- **Events**: PRE/POST_AGENT_LOOP, PRE/POST_TOOL_USE, PRE/POST_CHECKPOINT_SAVE, PRE/POST_INTERRUPT
- **Production Security**: RBAC authorization, Ed25519 signature verification, process isolation with resource limits, API key authentication for metrics, sensitive data redaction, rate limiting, input validation, audit trails
- **Compliance**: PCI DSS 4.0, HIPAA § 164.312, GDPR Article 32, SOC2
- **Examples**: `examples/autonomy/hooks/` (audit_trail, distributed_tracing, prometheus_metrics)
- **Docs**: `docs/features/hooks-system.md`, `docs/guides/hooks-system-guide.md`

### Multi-Agent Patterns
- **Supervisor-Worker**: Central coordinator with specialized workers
- **Agent-to-Agent**: Direct peer communication
- **Shared Memory**: Coordinated state management
- **Hierarchical**: Nested agent structures

### Multimodal Support
- **Vision**: Image understanding and analysis
- **Audio**: Speech and sound processing
- **Text**: Natural language processing
- **Orchestration**: Coordinating multiple modalities

## When to Use This Skill

Use Kaizen when you need to:
- Build AI agents with type-safe interfaces
- Implement multi-agent systems with orchestration patterns
- Process multimodal inputs (vision, audio, text)
- Create RAG (Retrieval-Augmented Generation) systems
- Implement chain-of-thought reasoning
- Build supervisor-worker or ensemble architectures
- Track costs and performance of AI agents
- Add zero-code-change observability to agents (hooks system)
- Monitor, trace, and audit agent behavior in production
- Secure agent observability with RBAC, process isolation, and compliance controls
- Create production-ready agentic applications

**Use Pipeline Patterns When:**
- **Ensemble**: Need diverse perspectives synthesized (code review, research, analysis)
- **Blackboard**: Iterative problem-solving (optimization, debugging, planning)
- **Router**: Intelligent task delegation to specialists
- **Parallel**: Bulk processing or voting-based consensus
- **Sequential**: Linear workflows with dependency chains

## Integration Patterns

### With DataFlow (Data-Driven Agents)
```python
from kaizen.core.base_agent import BaseAgent
from dataflow import DataFlow
from dataclasses import dataclass

@dataclass
class DataAgentConfig:
    llm_provider: str = "openai"
    model: str = "gpt-4"

# Agent that works with database
class DataAgent(BaseAgent):
    def __init__(self, config: DataAgentConfig, db: DataFlow):
        self.db = db
        super().__init__(config=config, signature=MySignature())
```

### With Nexus (Multi-Channel Agents)
```python
from kaizen.core.base_agent import BaseAgent
from nexus import Nexus

# Deploy agents via API/CLI/MCP
agent_workflow = create_agent_workflow()
nexus = Nexus([agent_workflow])
nexus.run()  # Agents available via all channels
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

## Critical Rules

- ✅ Define signatures before implementing agents
- ✅ Extend BaseAgent for production agents
- ✅ Use type hints in signatures for validation
- ✅ Track costs in production environments
- ✅ Test agents with real infrastructure (NO MOCKING)
- ❌ NEVER skip signature definitions
- ❌ NEVER ignore cost tracking in production
- ❌ NEVER mock LLM calls in integration tests

## Version Compatibility

- **Current Version**: Latest Kaizen release
- **Core SDK Version**: 0.9.25+
- **Python**: 3.8+
- **LLM Support**: OpenAI, Anthropic, local models

## Related Skills

- **[01-core-sdk](../../01-core-sdk/SKILL.md)** - Core workflow patterns
- **[02-dataflow](../dataflow/SKILL.md)** - Database integration
- **[03-nexus](../nexus/SKILL.md)** - Multi-channel deployment
- **[05-mcp](../mcp/SKILL.md)** - MCP server integration
- **[17-gold-standards](../../17-gold-standards/SKILL.md)** - Best practices

## Support

For Kaizen-specific questions, invoke:
- `kaizen-specialist` - Kaizen framework implementation
- `testing-specialist` - Agent testing strategies
- `framework-advisor` - When to use Kaizen vs other frameworks
