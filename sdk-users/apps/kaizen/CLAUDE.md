# Kaizen - Quick Reference for Claude Code

## 🚀 What is Kaizen?

**Kaizen** is a signature-based AI agent framework built on Kailash Core SDK, providing production-ready agents with multi-modal processing, multi-agent coordination, and enterprise features.

## ⚡ Quick Start

### Basic Agent Usage

```python
from kaizen.agents import SimpleQAAgent
from dataclasses import dataclass

# Zero-config usage
agent = SimpleQAAgent(QAConfig())
result = agent.ask("What is AI?")
print(result["answer"])  # Direct answer access

# Progressive configuration
@dataclass
class CustomConfig:
    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 500

agent = SimpleQAAgent(CustomConfig())
```

### Multi-Modal Processing

```python
from kaizen.agents import VisionAgent, VisionAgentConfig

# Vision agent with Ollama
config = VisionAgentConfig(
    llm_provider="ollama",
    model="bakllava"  # or "llava"
)
agent = VisionAgent(config=config)

result = agent.analyze(
    image="/path/to/image.png",  # File path, NOT base64
    question="What is in this image?"  # 'question', NOT 'prompt'
)
print(result['answer'])  # Key is 'answer', NOT 'response'
```

### Multi-Agent Coordination

```python
from kaizen.agents.coordination.supervisor_worker import SupervisorWorkerPattern

# Semantic capability matching (NO hardcoded if/else!)
pattern = SupervisorWorkerPattern(supervisor, workers, coordinator, shared_pool)

# A2A automatically selects best worker
best_worker = pattern.supervisor.select_worker_for_task(
    task="Analyze sales data and create visualization",
    available_workers=[code_expert, data_expert, writing_expert],
    return_score=True
)
# Returns: {"worker": <DataAnalystAgent>, "score": 0.9}
```

## 🎯 Core API

### Available Specialized Agents

**Implemented and Production-Ready (v0.2.0):**
```python
from kaizen.agents import (
    # Single-Agent Patterns (8 agents)
    SimpleQAAgent,           # Question answering
    ChainOfThoughtAgent,     # Step-by-step reasoning
    ReActAgent,              # Reasoning + action cycles
    RAGResearchAgent,        # Research with retrieval
    CodeGenerationAgent,     # Code generation
    MemoryAgent,             # Memory-enhanced conversations

    # Multi-Modal Agents (2 agents)
    VisionAgent,             # Image analysis (Ollama + OpenAI GPT-4V)
    TranscriptionAgent,      # Audio transcription (Whisper)
)
```

### Tool Calling (NEW in v0.2.0)

**Autonomous tool execution with approval workflows:**
```python
from kaizen.core.base_agent import BaseAgent
from kaizen.tools import ToolRegistry
from kaizen.tools.builtin import register_builtin_tools

# Setup tool registry
registry = ToolRegistry()
register_builtin_tools(registry)  # 12 builtin tools

# Create agent with tool support
agent = BaseAgent(
    config=config,
    signature=signature,
    tool_registry=registry  # Enable tool calling
)

# Discover tools
tools = await agent.discover_tools(category="file")

# Execute single tool
result = await agent.execute_tool("read_file", {"path": "data.txt"})

# Chain multiple tools
results = await agent.execute_tool_chain([
    {"tool_name": "read_file", "params": {"path": "input.txt"}},
    {"tool_name": "write_file", "params": {"path": "output.txt", "content": "..."}}
])
```

**12 Builtin Tools:**
- **File (5)**: read_file, write_file, delete_file, list_directory, file_exists
- **HTTP (4)**: http_get, http_post, http_put, http_delete
- **Bash (1)**: bash_command
- **Web (2)**: fetch_url, extract_links

### Control Protocol (NEW in v0.2.0)

**Bidirectional agent ↔ client communication:**
```python
from kaizen.core.autonomy.control import ControlProtocol
from kaizen.core.autonomy.control.transports import CLITransport

# Create bidirectional protocol
protocol = ControlProtocol(CLITransport())
await protocol.start()

# Agent asks questions during execution
answer = await agent.ask_user_question("Which option?", ["A", "B", "C"])

# Agent requests approval for dangerous operations
approved = await agent.request_approval("Delete files?", details)

# Agent reports progress
await agent.report_progress("Processing...", percentage=50)
```

**4 Transports:** CLI, HTTP/SSE, stdio, memory

### Agent Architecture Pattern

All agents follow the same BaseAgent pattern:

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from dataclasses import dataclass

# 1. Define configuration
@dataclass
class MyConfig:
    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.7
    # BaseAgent auto-extracts: llm_provider, model, temperature, max_tokens, provider_config

# 2. Define signature (inputs/outputs)
class MySignature(Signature):
    question: str = InputField(desc="User input")
    answer: str = OutputField(desc="Agent output")

# 3. Extend BaseAgent
class MyAgent(BaseAgent):
    def __init__(self, config: MyConfig):
        super().__init__(config=config, signature=MySignature())

    def ask(self, question: str):
        return self.run(question=question)
```

## 📚 Documentation Structure

### Getting Started
- **[Installation](docs/getting-started/installation.md)** - Setup and dependencies
- **[Quickstart](docs/getting-started/quickstart.md)** - Your first Kaizen agent
- **[First Agent](docs/getting-started/first-agent.md)** - Detailed agent creation

### Core Guides
- **[Signature Programming](docs/guides/signature-programming.md)** - Type-safe I/O with Signatures
- **[BaseAgent Architecture](docs/guides/baseagent-architecture.md)** - Unified agent system
- **[Multi-Modal Processing](docs/guides/multi-modal.md)** - Vision and audio agents
- **[Multi-Agent Coordination](docs/guides/multi-agent.md)** - Google A2A protocol patterns

### Reference
- **[API Reference](docs/reference/api-reference.md)** - Complete API documentation
- **[Configuration Guide](docs/reference/configuration.md)** - All config options
- **[Troubleshooting](docs/reference/troubleshooting.md)** - Common issues

### Examples
- **[Single-Agent Patterns](../../../apps/kailash-kaizen/examples/1-single-agent/)** - 10 basic patterns
- **[Multi-Agent Patterns](../../../apps/kailash-kaizen/examples/2-multi-agent/)** - 6 coordination patterns
- **[Enterprise Workflows](../../../apps/kailash-kaizen/examples/3-enterprise-workflows/)** - 5 production patterns
- **[Advanced RAG](../../../apps/kailash-kaizen/examples/4-advanced-rag/)** - 5 RAG techniques
- **[MCP Integration](../../../apps/kailash-kaizen/examples/5-mcp-integration/)** - 5 MCP patterns
- **[Multi-Modal](../../../apps/kailash-kaizen/examples/8-multi-modal/)** - Vision/audio examples

## 🔧 Common Patterns

### Basic Agent Pattern
```python
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig

config = QAConfig(
    llm_provider="openai",
    model="gpt-4",
    temperature=0.7
)

agent = SimpleQAAgent(config)
result = agent.ask("What is quantum computing?")

# UX: One-line field extraction (built into BaseAgent)
answer = result.get("answer", "No answer")
confidence = result.get("confidence", 0.0)
```

### Memory-Enabled Agent
```python
# Enable memory with max_turns parameter
config = QAConfig(
    llm_provider="openai",
    model="gpt-4",
    max_turns=10  # Enable BufferMemory (None = disabled)
)

agent = SimpleQAAgent(config)

# Use session_id for memory continuity
result1 = agent.ask("My name is Alice", session_id="user123")
result2 = agent.ask("What's my name?", session_id="user123")
# Returns: "Your name is Alice"
```

### Vision Processing
```python
from kaizen.agents import VisionAgent, VisionAgentConfig

# Ollama vision (free, local)
config = VisionAgentConfig(
    llm_provider="ollama",
    model="bakllava"
)
agent = VisionAgent(config=config)

result = agent.analyze(
    image="/path/to/receipt.jpg",
    question="What is the total amount?"
)
```

### Multi-Agent Coordination
```python
from kaizen.agents.coordination.supervisor_worker import SupervisorWorkerPattern
from kaizen.agents import SimpleQAAgent, CodeGenerationAgent, RAGResearchAgent

# Create worker agents
qa_agent = SimpleQAAgent(config=QAConfig())
code_agent = CodeGenerationAgent(config=CodeConfig())
research_agent = RAGResearchAgent(config=RAGConfig())

# Create pattern with automatic A2A capability matching
pattern = SupervisorWorkerPattern(
    supervisor=supervisor_agent,
    workers=[qa_agent, code_agent, research_agent],
    coordinator=coordinator,
    shared_pool=shared_memory_pool
)

# Semantic task routing (no hardcoded logic!)
result = pattern.execute_task("Analyze this codebase and suggest improvements")
```

## ⚠️ Common Mistakes to Avoid

### 1. Wrong Vision Agent Parameters
```python
# ❌ WRONG: Using 'prompt' instead of 'question'
result = agent.analyze(image=img, prompt="What is this?")

# ❌ WRONG: Using 'response' key
answer = result['response']

# ❌ WRONG: Passing base64 string
result = agent.analyze(image=base64_string, question="...")

# ✅ CORRECT: Use 'question' parameter and 'answer' key
result = agent.analyze(image="/path/to/image.png", question="What is this?")
answer = result['answer']
```

### 2. Missing API Keys
```python
# ❌ WRONG: Not loading .env
agent = SimpleQAAgent(QAConfig(llm_provider="openai"))

# ✅ CORRECT: Load .env first
from dotenv import load_dotenv
load_dotenv()  # Loads OPENAI_API_KEY from .env
agent = SimpleQAAgent(QAConfig(llm_provider="openai"))
```

### 3. Incorrect Configuration Pattern
```python
# ❌ WRONG: Using BaseAgentConfig directly
config = BaseAgentConfig(model="gpt-4")  # Don't do this!

# ✅ CORRECT: Use domain config (auto-converted to BaseAgentConfig)
config = QAConfig(model="gpt-4")
agent = SimpleQAAgent(config)  # Auto-extraction happens here
```

## 🏗️ Architecture

### Framework Position
```
┌─────────────────────────────────────────────────────────────┐
│                    Kaizen Framework                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  BaseAgent  │  │ Multi-Modal │  │  Multi-     │        │
│  │ Architecture│  │  Processing │  │  Agent      │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
│                           │                                 │
│  ┌─────────────────────────────────────────────────────┐  │
│  │          Kailash Core SDK                           │  │
│  │  WorkflowBuilder │ LocalRuntime │ 110+ Nodes       │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Core Components

1. **BaseAgent** (`src/kaizen/core/base_agent.py`)
   - Unified agent system with lazy initialization
   - Auto-generates A2A capability cards (`to_a2a_card()`)
   - Strategy pattern execution (AsyncSingleShotStrategy default)
   - Production-ready with 100% test coverage

2. **Signature Programming** (`src/kaizen/signatures/`)
   - Type-safe I/O with InputField/OutputField
   - SignatureParser, SignatureCompiler, SignatureValidator
   - Enterprise extensions, Multi-modal support
   - 107 exported components

3. **Multi-Modal Processing** (`src/kaizen/agents/`)
   - Vision: Ollama (llava, bakllava) + OpenAI GPT-4V
   - Audio: Whisper transcription
   - Unified orchestration with MultiModalAgent
   - Real infrastructure testing (NO MOCKING)

4. **Multi-Agent Coordination** (`src/kaizen/agents/coordination/`)
   - Google A2A protocol integration (100% compliant)
   - SupervisorWorkerPattern with semantic matching (14/14 tests)
   - 4 additional patterns: Consensus, Debate, Sequential, Handoff
   - Automatic capability discovery, no hardcoded selection

## 🧪 Testing

### 3-Tier Testing Strategy
1. **Tier 1 (Unit)**: Fast, mocked LLM providers
2. **Tier 2 (Integration)**: Real Ollama inference (local, free)
3. **Tier 3 (E2E)**: Real OpenAI inference (paid API, budget-controlled)

**CRITICAL**: NO MOCKING in Tiers 2-3 (real infrastructure only)

### Test Execution
```bash
# Run all tests
pytest

# Run Tier 1 only (fast, mocked)
pytest tests/unit/

# Run Tier 2 (Ollama integration - requires Ollama running)
pytest tests/integration/test_ollama_validation.py

# Run Tier 3 (OpenAI - requires API key in .env)
pytest tests/integration/test_multi_modal_integration.py
```

## 🚦 Production Deployment

### Environment Configuration
```bash
# Required API Keys (.env)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Optional Configuration
KAIZEN_LOG_LEVEL=INFO
KAIZEN_PERFORMANCE_TRACKING=true
KAIZEN_ERROR_HANDLING=true
```

### Integration with DataFlow
```python
from dataflow import DataFlow
from kaizen.agents import SimpleQAAgent

# DataFlow for database operations
db = DataFlow()

@db.model
class QASession:
    question: str
    answer: str
    confidence: float

# Kaizen for AI processing
agent = SimpleQAAgent(QAConfig())
result = agent.ask("What is the capital of France?")

# Store in database via workflow
workflow = WorkflowBuilder()
workflow.add_node("QASessionCreateNode", "store", {
    "question": result["question"],
    "answer": result["answer"],
    "confidence": result["confidence"]
})
```

### Integration with Nexus
```python
from nexus import Nexus
from kaizen.agents import SimpleQAAgent

# Create Nexus platform
nexus = Nexus(
    title="AI Q&A Platform",
    enable_api=True,
    enable_cli=True,
    enable_mcp=True
)

# Deploy Kaizen agent
agent = SimpleQAAgent(QAConfig())
agent_workflow = agent.to_workflow()
nexus.register("qa_agent", agent_workflow.build())

# Available on all channels:
# - API: POST /workflows/qa_agent
# - CLI: nexus run qa_agent
# - MCP: qa_agent tool for AI assistants
```

## 💡 Tips

1. **API Keys in .env**: Always check `.env` file before asking user for API keys
2. **Use Actual Imports**: Import from `kaizen.agents`, not conceptual packages
3. **BaseAgent Pattern**: All custom agents should extend `BaseAgent`
4. **Config Auto-Extraction**: Use domain configs, BaseAgent auto-converts
5. **Multi-Modal API**: Use 'question' parameter and 'answer' key (not 'prompt'/'response')
6. **Memory Opt-In**: Set `max_turns` in config to enable BufferMemory
7. **Real Infrastructure**: Test with Ollama (Tier 2) before OpenAI (Tier 3)

## 🔗 Related Documentation

- **[Main Kaizen Docs](../../../apps/kailash-kaizen/CLAUDE.md)** - Complete framework documentation
- **[Kaizen Examples](../../../apps/kailash-kaizen/examples/)** - 35+ working implementations
- **[Core SDK](../../2-core-concepts/)** - Foundation patterns
- **[DataFlow](../dataflow/)** - Database framework integration
- **[Nexus](../nexus/)** - Multi-channel platform integration

---

**For SDK details**: See [Kailash SDK Documentation](../../../CLAUDE.md)
**For examples**: See [Kaizen Examples](../../../apps/kailash-kaizen/examples/)
