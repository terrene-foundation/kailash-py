# Kaizen Framework Documentation

Kaizen is a signature-based AI agent framework built on Kailash Core SDK for production-ready AI agents with multi-modal processing, multi-agent coordination, and enterprise features.

## Quick Links

- **[README.md](../README.md)** - Framework overview and quick start
- **[CLAUDE.md](../CLAUDE.md)** - Quick reference for Claude Code
- **[Examples](../examples/README.md)** - Working code examples

## Documentation Structure

```
docs/
├── getting-started/
│   ├── installation.md     # Setup and dependencies
│   ├── quickstart.md       # Your first agent (5 minutes)
│   └── first-agent.md      # Detailed agent creation
├── guides/
│   ├── signature-programming.md      # Type-safe I/O with Signatures
│   ├── baseagent-architecture.md     # Unified agent system
│   ├── multi-agent-coordination.md   # Google A2A protocol patterns
│   ├── hooks-system.md               # Event-driven monitoring
│   ├── planning-agents-guide.md      # PlanningAgent & PEVAgent
│   ├── meta-controller-routing-guide.md  # Intelligent task delegation
│   ├── control-protocol-tutorial.md  # Bidirectional communication
│   ├── integration-patterns.md       # DataFlow, Nexus, MCP
│   └── ollama-quickstart.md          # Local LLM setup
├── reference/
│   ├── api-reference.md              # Complete API documentation
│   ├── configuration.md              # All config options
│   ├── memory-patterns-guide.md      # Memory usage patterns
│   ├── strategy-selection-guide.md   # Execution strategy selection
│   ├── control-protocol-api.md       # Control protocol reference
│   ├── multi-modal-api-reference.md  # Vision and audio APIs
│   └── troubleshooting.md            # Common issues
└── advanced/
    └── README.md                     # Advanced topics
```

## Getting Started

### 1. Installation

```bash
pip install kailash-kaizen
```

### 2. Your First Agent

```python
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig
from dotenv import load_dotenv

load_dotenv()  # Load API keys from .env

config = QAConfig(llm_provider="openai", model="gpt-4")
agent = SimpleQAAgent(config)
result = agent.ask("What is AI?")
print(result["answer"])
```

### 3. Learn More

- **Signatures**: [guides/signature-programming.md](guides/signature-programming.md) - Type-safe I/O
- **Multi-Agent**: [guides/multi-agent-coordination.md](guides/multi-agent-coordination.md) - A2A protocol
- **Vision/Audio**: [reference/multi-modal-api-reference.md](reference/multi-modal-api-reference.md) - Multi-modal

## Key Concepts

| Concept | Description | Guide |
|---------|-------------|-------|
| **Signature** | Type-safe input/output definitions | [signature-programming.md](guides/signature-programming.md) |
| **BaseAgent** | Unified agent architecture | [baseagent-architecture.md](guides/baseagent-architecture.md) |
| **A2A Protocol** | Multi-agent coordination | [multi-agent-coordination.md](guides/multi-agent-coordination.md) |
| **Hooks** | Event-driven monitoring | [hooks-system.md](guides/hooks-system.md) |
| **Journey** | Multi-pathway user flows | [CLAUDE.md](../CLAUDE.md#journey-orchestration) |

## Integration

- **DataFlow**: Database operations with auto-generated nodes
- **Nexus**: Deploy agents as API/CLI/MCP simultaneously
- **MCP**: Model Context Protocol for tool calling

See [integration-patterns.md](guides/integration-patterns.md) for details.
