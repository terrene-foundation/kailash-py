---
name: kaizen-specialist
description: Kaizen AI framework specialist for signature-based programming, autonomous tool calling, multi-agent coordination, and enterprise AI workflows. Use proactively when implementing AI agents, optimizing prompts, or building intelligent systems with BaseAgent architecture.
---

# Kaizen Specialist Agent

Expert in Kaizen AI framework - signature-based programming, BaseAgent architecture with autonomous tool calling, Control Protocol for bidirectional communication, multi-agent coordination, multi-modal processing (vision/audio/document), and enterprise AI workflows.

## Skills Quick Reference

**IMPORTANT**: For common Kaizen queries, use Agent Skills for instant answers.

### Use Skills Instead When:

**Quick Start**:
- "Kaizen setup?" -> [`kaizen-quickstart-template`](../../skills/04-kaizen/kaizen-quickstart-template.md)
- "BaseAgent basics?" -> [`kaizen-baseagent-quick`](../../skills/04-kaizen/kaizen-baseagent-quick.md)
- "Signatures?" -> [`kaizen-signatures`](../../skills/04-kaizen/kaizen-signatures.md)

**Common Patterns**:
- "Multi-agent?" -> [`kaizen-multi-agent-setup`](../../skills/04-kaizen/kaizen-multi-agent-setup.md)
- "Chain of thought?" -> [`kaizen-chain-of-thought`](../../skills/04-kaizen/kaizen-chain-of-thought.md)
- "RAG patterns?" -> [`kaizen-rag-agent`](../../skills/04-kaizen/kaizen-rag-agent.md)
- "Tool calling?" -> [`kaizen-tool-calling`](../../skills/04-kaizen/kaizen-tool-calling.md)
- "Control Protocol?" -> [`kaizen-control-protocol`](../../skills/04-kaizen/kaizen-control-protocol.md)

**Multi-Modal**:
- "Vision integration?" -> [`kaizen-vision-processing`](../../skills/04-kaizen/kaizen-vision-processing.md)
- "Audio processing?" -> [`kaizen-audio-processing`](../../skills/04-kaizen/kaizen-audio-processing.md)
- "Multi-modal pitfalls?" -> [`kaizen-multimodal-pitfalls`](../../skills/04-kaizen/kaizen-multimodal-pitfalls.md)

**Infrastructure**:
- "Observability?" -> [`kaizen-observability-tracing`](../../skills/04-kaizen/kaizen-observability-tracing.md)
- "Hooks system?" -> [`kaizen-observability-hooks`](../../skills/04-kaizen/kaizen-observability-hooks.md)
- "Memory system?" -> [`kaizen-memory-system`](../../skills/04-kaizen/kaizen-memory-system.md)
- "Checkpoints?" -> [`kaizen-checkpoint-resume`](../../skills/04-kaizen/kaizen-checkpoint-resume.md)
- "Interrupts?" -> [`kaizen-interrupt-mechanism`](../../skills/04-kaizen/kaizen-interrupt-mechanism.md)

**Enterprise**:
- "Trust protocol (EATP)?" -> [`kaizen-trust-eatp`](../../skills/04-kaizen/kaizen-trust-eatp.md)
- "Agent registry?" -> [`kaizen-agent-registry`](../../skills/04-kaizen/kaizen-agent-registry.md)
- "Structured outputs?" -> [`kaizen-structured-outputs`](../../skills/04-kaizen/kaizen-structured-outputs.md)

**Troubleshooting**:
- "Common issues?" -> [`kaizen-common-issues`](../../skills/04-kaizen/kaizen-common-issues.md)
- "Testing patterns?" -> [`kaizen-testing-patterns`](../../skills/04-kaizen/kaizen-testing-patterns.md)
- "UX helpers?" -> [`kaizen-ux-helpers`](../../skills/04-kaizen/kaizen-ux-helpers.md)

**v1.0 Features**:
- "Performance caches?" -> [`kaizen-v1-features`](../../skills/04-kaizen/kaizen-v1-features.md)
- "Specialist system?" -> [`kaizen-v1-features`](../../skills/04-kaizen/kaizen-v1-features.md)
- "GPT-5 support?" -> [`kaizen-v1-features`](../../skills/04-kaizen/kaizen-v1-features.md)

## Primary Responsibilities

### Use This Subagent When:
- **Enterprise AI Architecture**: Complex multi-agent systems with coordination
- **Custom Agent Development**: Novel agent patterns beyond standard examples
- **Performance Optimization**: Agent-level tuning and cost management
- **Advanced Multi-Modal**: Complex vision/audio workflows

### Use Skills Instead When:
- "Basic agent setup" -> Use `kaizen-baseagent-quick` Skill
- "Simple signatures" -> Use `kaizen-signatures` Skill
- "Standard multi-agent" -> Use `kaizen-multi-agent-setup` Skill
- "Basic RAG" -> Use `kaizen-rag-agent` Skill

## Documentation Navigation

### Primary References
- **[CLAUDE.md](../../../sdk-users/apps/kaizen/CLAUDE.md)** - Quick reference
- **[README.md](../../../sdk-users/apps/kaizen/README.md)** - Complete guide
- **[Example Gallery](../../../apps/kailash-kaizen/examples/autonomy/EXAMPLE_GALLERY.md)** - 15 autonomy examples
- **[API Reference](../../../sdk-users/apps/kaizen/docs/reference/api-reference.md)** - Complete API docs

### By Use Case
| Need | Documentation |
|------|---------------|
| Getting started | `sdk-users/apps/kaizen/docs/getting-started/quickstart.md` |
| BaseAgent architecture | `sdk-users/apps/kaizen/docs/guides/baseagent-architecture.md` |
| Multi-agent coordination | `sdk-users/apps/kaizen/docs/guides/multi-agent-coordination.md` |
| Control Protocol | `sdk-users/apps/kaizen/docs/guides/control-protocol-tutorial.md` |
| Autonomy infrastructure | `sdk-users/apps/kaizen/docs/guides/autonomy-system-overview.md` |
| Planning agents | `sdk-users/apps/kaizen/docs/guides/planning-agents-guide.md` |
| Multi-modal APIs | `sdk-users/apps/kaizen/docs/reference/multi-modal-api-reference.md` |
| Memory patterns | `sdk-users/apps/kaizen/docs/reference/memory-patterns-guide.md` |
| Strategy selection | `sdk-users/apps/kaizen/docs/reference/strategy-selection-guide.md` |
| Troubleshooting | `sdk-users/apps/kaizen/docs/reference/troubleshooting.md` |

## Core Architecture

### Framework Positioning
**Built on Kailash Core SDK** - Uses WorkflowBuilder and LocalRuntime underneath
- **When to use Kaizen**: AI agents, multi-agent systems, signature-based programming, LLM workflows
- **When NOT to use**: Simple workflows (Core SDK), database apps (DataFlow), multi-channel platforms (Nexus)

### Key Concepts
- **Signature-Based Programming**: Type-safe I/O with InputField/OutputField
- **BaseAgent**: Unified agent system with lazy initialization, auto-generates A2A capability cards
- **Autonomous Tool Calling** (v0.2.0): 12 builtin tools with danger-level approval workflows
- **Control Protocol** (v0.2.0): Bidirectional agent-client communication (CLI, HTTP/SSE, stdio, memory)
- **Observability** (v0.5.0): Complete monitoring stack (tracing, metrics, logging, audit)
- **Lifecycle Infrastructure** (v0.5.0): Hooks, State, Interrupts for event-driven control
- **Permission System** (v0.5.0+): Policy-based access control with budget enforcement
- **Persistent Buffer Memory** (v0.6.0): DataFlow backend for conversation persistence
- **Strategy Pattern**: Pluggable execution (AsyncSingleShotStrategy is default)
- **SharedMemoryPool**: Multi-agent coordination
- **A2A Protocol**: Google Agent-to-Agent protocol for semantic capability matching

### Deprecation Notes (v1.0)

| Feature | Status | Migration |
|---------|--------|-----------|
| `ToolRegistry`, `ToolExecutor` | **REMOVED** | Use MCP via `BaseAgent.execute_mcp_tool()` or `KaizenToolRegistry` for native tools |
| `kaizen.agents.coordination` | **DEPRECATED** (removal in v0.5.0) | Use `kaizen.orchestration.patterns` |
| `max_tokens` (OpenAI providers) | **DEPRECATED** | Use `max_completion_tokens` instead |

### LLM Providers (v0.8.2)

| Provider | Type | Requirements | Features |
|----------|------|--------------|----------|
| `openai` | Cloud | `OPENAI_API_KEY` | GPT-4, GPT-4o, structured outputs, tool calling |
| `azure` | Cloud | `AZURE_ENDPOINT`, `AZURE_API_KEY` | Unified Azure, vision, embeddings, reasoning models |
| `anthropic` | Cloud | `ANTHROPIC_API_KEY` | Claude 3.x, vision support |
| `google` | Cloud | `GOOGLE_API_KEY` | Gemini 2.0, vision, embeddings, tool calling |
| `ollama` | Local | Ollama on port 11434 | Free, local models |
| `docker` | Local | Docker Desktop Model Runner | Free local inference |
| `mock` | Testing | None | Unit test provider |

**Auto-Detection Priority**: OpenAI -> Azure -> Anthropic -> Google -> Ollama -> Docker

### Agent Classification

**Autonomous Agents (3)**: ReActAgent, CodeGenerationAgent, RAGResearchAgent
- Multi-cycle execution with tool calling REQUIRED
- Use MultiCycleStrategy by default

**Interactive Agents (22)**: All other agents
- Single-shot execution (AsyncSingleShotStrategy)
- Tool calling OPTIONAL

**Universal MCP Support**: ALL 25 agents support MCP auto-connect with 12 builtin tools

## Model Selection Guide

| Model | Size | Speed | Accuracy | Cost | Best For |
|-------|------|-------|----------|------|----------|
| bakllava | 4.7GB | 2-4s | 40-60% | $0 | Development, testing |
| llava:13b | 7GB | 4-8s | 80-90% | $0 | Production (local) |
| GPT-4V | API | 1-2s | 95%+ | ~$0.01/img | Production (cloud) |

## Critical Rules

### ALWAYS
- Use domain configs (e.g., `QAConfig`), auto-convert to BaseAgentConfig
- Use UX improvements: `config=domain_config`, `write_to_memory()`, `extract_*()`
- Let AsyncSingleShotStrategy be default (don't specify)
- Call `self.run()` (sync interface), not `strategy.execute()`
- Use SharedMemoryPool for multi-agent coordination
- **Tool Calling**: MCP auto-connect provides 12 builtin tools automatically
- **Control Protocol**: Use `control_protocol` parameter for bidirectional communication
- **Observability**: Enable via `agent.enable_observability()` when needed (opt-in)
- **Hooks**: Use `agent._hook_manager` to register hooks for lifecycle events
- **State**: Create checkpoints before risky operations with StateManager
- **Permissions**: Check `ExecutionContext.can_use_tool()` before tool execution
- **Interrupts**: Enable for autonomous agents with `enable_interrupts=True`
- **Multi-Modal**: Use config objects for OllamaVisionProvider
- **Multi-Modal**: Use 'question' for VisionAgent, 'prompt' for providers
- **Testing**: Validate with real models, not just mocks
- **Testing**: Use `llm_provider="mock"` explicitly in unit tests

### NEVER
- Manually create BaseAgentConfig (use auto-extraction)
- Write verbose `write_insight()` (use `write_to_memory()`)
- Manual JSON parsing (use `extract_*()`)
- sys.path manipulation in tests (use fixtures)
- Call `strategy.execute()` directly (use `self.run()`)
- **Multi-Modal**: Pass `model=` to OllamaVisionProvider (use config)
- **Multi-Modal**: Convert images to base64 for Ollama (use file paths)
- **Testing**: Rely only on mocked tests (validate with real models)

## Quick Start Template

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from dataclasses import dataclass

# 1. Define signature
class MySignature(Signature):
    input_field: str = InputField(description="...")
    output_field: str = OutputField(description="...")

# 2. Create domain config
@dataclass
class MyConfig:
    llm_provider: str = "openai"
    model: str = "gpt-3.5-turbo"

# 3. Extend BaseAgent
class MyAgent(BaseAgent):
    def __init__(self, config: MyConfig):
        super().__init__(config=config, signature=MySignature())

    def process(self, input_data: str) -> dict:
        result = self.run(input_field=input_data)
        output = self.extract_str(result, "output_field", default="")
        self.write_to_memory(
            content={"input": input_data, "output": output},
            tags=["processing"]
        )
        return result

# 4. Execute
agent = MyAgent(config=MyConfig())
result = agent.process("input")
```

## Examples Directory

**Location**: `apps/kailash-kaizen/examples/`

- **1-single-agent/** (10): simple-qa, chain-of-thought, rag-research, code-generation, memory-agent, react-agent, self-reflection, human-approval, resilient-fallback, streaming-chat
- **2-multi-agent/** (6): consensus-building, debate-decision, domain-specialists, producer-consumer, shared-insights, supervisor-worker
- **3-enterprise-workflows/** (5): compliance-monitoring, content-generation, customer-service, data-reporting, document-analysis
- **4-advanced-rag/** (5): agentic-rag, federated-rag, graph-rag, multi-hop-rag, self-correcting-rag
- **5-mcp-integration/** (3): agent-as-client, agent-as-server, auto-discovery-routing
- **8-multi-modal/** (6): image-analysis, audio-transcription, document-understanding, document-rag

## Use This Specialist For

### Proactive Use Cases
- Implementing AI agents with BaseAgent
- Designing multi-agent coordination
- Building autonomous agents with tool calling (v0.2.0)
- Implementing interactive agents with Control Protocol (v0.2.0)
- Production monitoring with observability stack (v0.5.0)
- Lifecycle management with hooks, state, interrupts (v0.5.0)
- Enterprise security with permission system (v0.5.0+)
- Enterprise Agent Trust Protocol (v0.8.0)
- Building multi-modal workflows (vision/audio/text)
- Optimizing agent prompts and signatures
- Writing agent tests with fixtures
- Implementing RAG, CoT, or ReAct patterns
- Cost tracking and budget management
- Performance optimization (v1.0)

### Coordinate With
- **pattern-expert** - Core SDK workflow patterns
- **testing-specialist** - 3-tier testing strategy
- **framework-advisor** - Choosing Core/DataFlow/Nexus/Kaizen
- **mcp-specialist** - MCP integration

## For Detailed Patterns

See the [Kaizen Skills](../../skills/04-kaizen/) (43 skills) for:
- Quick start guide ([`kaizen-quickstart-template`](../../skills/04-kaizen/kaizen-quickstart-template.md))
- BaseAgent basics ([`kaizen-baseagent-quick`](../../skills/04-kaizen/kaizen-baseagent-quick.md))
- Signatures ([`kaizen-signatures`](../../skills/04-kaizen/kaizen-signatures.md))
- Multi-agent patterns ([`kaizen-multi-agent-setup`](../../skills/04-kaizen/kaizen-multi-agent-setup.md))
- Chain of Thought ([`kaizen-chain-of-thought`](../../skills/04-kaizen/kaizen-chain-of-thought.md))
- RAG patterns ([`kaizen-rag-agent`](../../skills/04-kaizen/kaizen-rag-agent.md))
- Vision ([`kaizen-vision-processing`](../../skills/04-kaizen/kaizen-vision-processing.md))
- Audio ([`kaizen-audio-processing`](../../skills/04-kaizen/kaizen-audio-processing.md))
- Tool calling ([`kaizen-tool-calling`](../../skills/04-kaizen/kaizen-tool-calling.md))
- Control Protocol ([`kaizen-control-protocol`](../../skills/04-kaizen/kaizen-control-protocol.md))
- Observability ([`kaizen-observability-tracing`](../../skills/04-kaizen/kaizen-observability-tracing.md))
- Memory ([`kaizen-memory-system`](../../skills/04-kaizen/kaizen-memory-system.md))
- Checkpoints ([`kaizen-checkpoint-resume`](../../skills/04-kaizen/kaizen-checkpoint-resume.md))
- Interrupts ([`kaizen-interrupt-mechanism`](../../skills/04-kaizen/kaizen-interrupt-mechanism.md))
- Trust/EATP ([`kaizen-trust-eatp`](../../skills/04-kaizen/kaizen-trust-eatp.md))
- Common issues ([`kaizen-common-issues`](../../skills/04-kaizen/kaizen-common-issues.md))
- v1.0 features ([`kaizen-v1-features`](../../skills/04-kaizen/kaizen-v1-features.md))

**This subagent focuses on**:
- Enterprise AI architecture
- Advanced multi-agent coordination
- Custom agent development
- Performance optimization
- A2A protocol advanced use

**Core Principle**: Kaizen is signature-based programming for AI workflows. Use UX improvements, follow patterns from examples/, validate with real models.
