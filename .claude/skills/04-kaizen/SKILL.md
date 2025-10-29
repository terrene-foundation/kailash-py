---
name: kaizen
description: "Kailash Kaizen - production-ready AI agent framework with signature-based programming, multi-agent coordination, and enterprise features. Use when asking about 'AI agents', 'agent framework', 'BaseAgent', 'multi-agent systems', 'agent coordination', 'signatures', 'agent signatures', 'RAG agents', 'vision agents', 'audio agents', 'multimodal agents', 'agent prompts', 'prompt optimization', 'chain of thought', 'ReAct pattern', 'supervisor-worker', 'agent-to-agent communication', 'streaming agents', 'agent testing', 'agent memory', or 'agentic workflows'."
---

# Kailash Kaizen - AI Agent Framework

Kaizen is a production-ready AI agent framework built on Kailash Core SDK that provides signature-based programming and multi-agent coordination.

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
from kaizen.base import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField

# Define agent signature (type-safe interface)
class SummarizeSignature(Signature):
    text: str = InputField(description="Text to summarize")
    summary: str = OutputField(description="Generated summary")

# Create agent with signature
class SummaryAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            signature=SummarizeSignature,
            instructions="Summarize the input text concisely."
        )

# Execute
agent = SummaryAgent()
result = agent(text="Long text here...")
print(result.summary)
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

### Comprehensive Guides (sdk-users/)

For in-depth documentation, see `sdk-users/apps/kaizen/docs/`:

**Core Guides:**
- **[BaseAgent Architecture](../../../sdk-users/apps/kaizen/docs/guides/baseagent-architecture.md)** - Complete unified agent system guide
- **[Multi-Agent Coordination](../../../sdk-users/apps/kaizen/docs/guides/multi-agent-coordination.md)** - Google A2A protocol, 5 coordination patterns
- **[Signature Programming](../../../sdk-users/apps/kaizen/docs/guides/signature-programming.md)** - Complete signature system guide
- **[Control Protocol Tutorial](../../../sdk-users/apps/kaizen/docs/guides/control-protocol-tutorial.md)** - Bidirectional agent ↔ client communication
- **[Integration Patterns](../../../sdk-users/apps/kaizen/docs/guides/integration-patterns.md)** - DataFlow, Nexus, MCP integration

**Reference Documentation:**
- **[API Reference](../../../sdk-users/apps/kaizen/docs/reference/api-reference.md)** - Complete API documentation
- **[Control Protocol API](../../../sdk-users/apps/kaizen/docs/reference/control-protocol-api.md)** - Full control protocol reference
- **[Memory Patterns Guide](../../../sdk-users/apps/kaizen/docs/reference/memory-patterns-guide.md)** - Memory usage patterns
- **[Strategy Selection Guide](../../../sdk-users/apps/kaizen/docs/reference/strategy-selection-guide.md)** - When to use which strategy
- **[Configuration Guide](../../../sdk-users/apps/kaizen/docs/reference/configuration.md)** - All configuration options
- **[Troubleshooting](../../../sdk-users/apps/kaizen/docs/reference/troubleshooting.md)** - Common issues and solutions

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

### Advanced Features (v0.2.0+)
- **[kaizen-control-protocol](kaizen-control-protocol.md)** - **NEW** Bidirectional agent ↔ client communication
- **[kaizen-tool-calling](kaizen-tool-calling.md)** - **NEW** Autonomous tool execution with approval workflows
- **[kaizen-streaming](kaizen-streaming.md)** - Streaming agent responses
- **[kaizen-cost-tracking](kaizen-cost-tracking.md)** - Cost monitoring and optimization
- **[kaizen-ux-helpers](kaizen-ux-helpers.md)** - UX enhancement utilities

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
from kaizen.base import BaseAgent
from dataflow import DataFlow

# Agent that works with database
class DataAgent(BaseAgent):
    def __init__(self, db: DataFlow):
        self.db = db
        super().__init__(...)
```

### With Nexus (Multi-Channel Agents)
```python
from kaizen.base import BaseAgent
from nexus import Nexus

# Deploy agents via API/CLI/MCP
agent_workflow = create_agent_workflow()
nexus = Nexus([agent_workflow])
nexus.run()  # Agents available via all channels
```

### With Core SDK (Custom Workflows)
```python
from kaizen.base import BaseAgent
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
