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

## Reference Documentation

### Getting Started
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

### Multi-Agent Systems
- **[kaizen-multi-agent-setup](kaizen-multi-agent-setup.md)** - Multi-agent system setup
- **[kaizen-supervisor-worker](kaizen-supervisor-worker.md)** - Supervisor-worker coordination
- **[kaizen-a2a-protocol](kaizen-a2a-protocol.md)** - Agent-to-agent communication
- **[kaizen-shared-memory](kaizen-shared-memory.md)** - Shared memory between agents

### Multimodal Processing
- **[kaizen-multimodal-orchestration](kaizen-multimodal-orchestration.md)** - Multimodal coordination
- **[kaizen-vision-processing](kaizen-vision-processing.md)** - Vision and image processing
- **[kaizen-audio-processing](kaizen-audio-processing.md)** - Audio processing agents
- **[kaizen-multimodal-pitfalls](kaizen-multimodal-pitfalls.md)** - Common pitfalls and solutions

### Advanced Features
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
- Implement multi-agent systems
- Process multimodal inputs (vision, audio, text)
- Create RAG (Retrieval-Augmented Generation) systems
- Implement chain-of-thought reasoning
- Build supervisor-worker architectures
- Track costs and performance of AI agents
- Create production-ready agentic applications

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
