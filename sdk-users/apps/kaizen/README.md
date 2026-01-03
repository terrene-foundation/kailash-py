# Kaizen - Signature-Based AI Agent Framework

**Production-ready AI agents with multi-modal processing, multi-agent coordination, and enterprise features built on Kailash SDK**

Kaizen provides a unified BaseAgent architecture where you extend agents for specific use cases, define type-safe Signatures for inputs/outputs, and leverage automatic optimization, error handling, and audit trails.

## 🎯 What is Kaizen?

Kaizen transforms AI agent development through **signature-based programming** and a **unified BaseAgent architecture**. Instead of reinventing agent patterns, extend BaseAgent with domain-specific logic while inheriting production-grade features automatically.

### Core Value Propositions

**Traditional AI Agent Development:**
```python
# Build everything from scratch
class MyAgent:
    def __init__(self, model, temperature, ...):
        self.model = model  # Manual setup
        self.temperature = temperature
        self.memory = []  # Manual memory management
        # ... dozens of lines for error handling, logging, etc.

    def process(self, input_data):
        # Manual prompt construction, error handling, retry logic...
        pass
```

**Kaizen Signature-Based Development:**
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

# 2. Define signature (type-safe I/O)
class MySignature(Signature):
    question: str = InputField(desc="User question")  # 'description=' also works
    answer: str = OutputField(desc="Agent answer")

# 3. Extend BaseAgent (87% less code, production-ready)
class MyAgent(BaseAgent):
    def __init__(self, config: MyConfig):
        super().__init__(config=config, signature=MySignature())

    def ask(self, question: str):
        return self.run(question=question)  # Auto: logging, error handling, performance tracking
```

**Key Benefits:**
- **Unified Architecture**: BaseAgent provides common infrastructure (87% code reduction)
- **Type-Safe Signatures**: Define inputs/outputs, framework handles validation
- **Auto-Optimization**: Automatic async execution, lazy initialization, performance tracking
- **Enterprise Ready**: Built-in error handling, logging, audit trails, memory management
- **Multi-Modal**: Vision (Ollama + OpenAI GPT-4V), Audio (Whisper)
- **Multi-Agent**: Google A2A protocol for semantic capability matching
- **Autonomous Tool Calling**: 12 builtin tools with approval workflows
- **Bidirectional Control Protocol**: Agent ↔ client communication (questions, approvals, progress)
- **Production Observability**: Complete monitoring stack (Jaeger, Prometheus, Grafana, ELK) with zero overhead
- **Core SDK Compatible**: Seamless integration with Kailash workflows

## 🆕 What's New in v0.6.0

**Enhanced Autonomy & Memory Systems** (Released 2025-10-29):

### Interrupt Mechanism (Production-Ready)
Complete graceful shutdown with checkpoint preservation:
- **3 Interrupt Sources**: USER (Ctrl+C), SYSTEM (timeout/budget), PROGRAMMATIC (API/hooks)
- **2 Shutdown Modes**: GRACEFUL (finish cycle + checkpoint) vs IMMEDIATE (stop now)
- **Signal Propagation**: Parent interrupts cascade to children
- **34 E2E Tests**: Production-validated
- **Examples**: `examples/autonomy/interrupts/` (ctrl_c, timeout, budget)

### Persistent Buffer Memory (DataFlow Backend)
Conversation persistence with dual-buffer architecture:
- **Dual-Buffer**: In-memory buffer (<1ms retrieval) + database storage
- **Auto-Persist**: Configurable auto-persist interval (every N messages)
- **JSONL Compression**: 60%+ storage reduction
- **Cross-Session**: Load conversation history across restarts
- **Multi-Instance**: Agent-specific memory isolation
- **28 E2E Tests**: Real database operations validated

### Enhanced Hooks System
- **New Events**: PRE/POST_INTERRUPT, PRE/POST_CHECKPOINT_SAVE
- **Performance**: <0.01ms overhead (625x better than target)
- **Production**: 100+ concurrent hooks supported

**Version**: 0.6.0 | **Dependencies**: Kailash >=0.10.2

---

## 🎯 OpenAI Structured Outputs

**Guaranteed schema compliance** with OpenAI's Structured Outputs API - ensure LLM responses always match your signature's structure.

### Usage

```python
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.core.structured_output import create_structured_output_config
from kaizen.signatures import Signature, InputField, OutputField

# Define signature
class ProductAnalysisSignature(Signature):
    product_description: str = InputField(desc="Product to analyze")
    category: str = OutputField(desc="Product category")
    price_range: str = OutputField(desc="Price estimate")
    confidence: float = OutputField(desc="Confidence 0-1")

# Enable structured outputs
config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4o-2024-08-06",  # Required for strict mode
    provider_config=create_structured_output_config(
        signature=ProductAnalysisSignature(),
        strict=True,  # 100% schema compliance
        name="product_analysis"
    )
)

agent = BaseAgent(config=config, signature=ProductAnalysisSignature())
result = agent.run(product_description="Wireless headphones")

# Response guaranteed to have all fields
print(result['category'])      # Always present
print(result['price_range'])   # Always present
print(result['confidence'])    # Always present, correct type
```

### Modes

- **Strict Mode** (`strict=True`): 100% schema compliance, requires `gpt-4o-2024-08-06+`
- **Legacy Mode** (`strict=False`): Best-effort compliance (~70-85%), works with all models

**Learn More**: [Structured Outputs Guide](docs/guides/signature-programming.md)

---

## 🚀 Quick Start

### Installation

```bash
# Install Kaizen framework
pip install kailash-kaizen

# Or specific version
pip install kailash-kaizen==0.6.0
```

### Your First Agent (3 Steps)

```python
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig
from dotenv import load_dotenv

# Load API keys from .env
load_dotenv()

# 1. Create config
config = QAConfig(
    llm_provider="openai",
    model="gpt-4"
)

# 2. Create agent
agent = SimpleQAAgent(config)

# 3. Execute
result = agent.ask("What is quantum computing?")
print(result["answer"])
print(f"Confidence: {result['confidence']}")
```

### Production Agent with Memory

```python
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig

# Enable memory with max_turns parameter
config = QAConfig(
    llm_provider="openai",
    model="gpt-4",
    max_turns=10  # Enable BufferMemory
)

agent = SimpleQAAgent(config)

# Use session_id for memory continuity
result1 = agent.ask("My name is Alice", session_id="user123")
result2 = agent.ask("What's my name?", session_id="user123")
print(result2["answer"])  # "Your name is Alice"
```

## 🔧 LLM Provider Configuration (v0.8.2)

Kaizen supports 9 LLM providers with automatic detection:

| Provider | Type | Requirements | Features |
|----------|------|--------------|----------|
| `openai` | Cloud | `OPENAI_API_KEY` | GPT-4, GPT-4o, structured outputs, tool calling |
| `azure` | Cloud | `AZURE_AI_INFERENCE_ENDPOINT`, `AZURE_AI_INFERENCE_API_KEY` | Azure AI Foundry, vision, embeddings, structured outputs |
| `anthropic` | Cloud | `ANTHROPIC_API_KEY` | Claude 3.x, vision support |
| `google` | Cloud | `GOOGLE_API_KEY` or `GEMINI_API_KEY` | Gemini 2.0, vision, embeddings, tool calling, structured outputs |
| `ollama` | Local | Ollama running on port 11434 | Free, local models (llama, mistral, etc.) |
| `docker` | Local | Docker Desktop Model Runner on port 12434 | Free local inference, GPU acceleration |
| `cohere` | Cloud | `COHERE_API_KEY` | Command models, embeddings |
| `huggingface` | Local | None (optional API key) | Sentence transformers, embeddings |
| `mock` | Testing | None | Unit test provider, no API calls |

### Provider Configuration Examples

```python
from dataclasses import dataclass

# OpenAI (default, recommended for production)
@dataclass
class OpenAIConfig:
    llm_provider: str = "openai"
    model: str = "gpt-4o-mini"
    temperature: float = 0.7

# Azure AI Foundry
# Prerequisites: export AZURE_AI_INFERENCE_ENDPOINT="https://your-endpoint.azure.com"
#               export AZURE_AI_INFERENCE_API_KEY="your-key"
@dataclass
class AzureConfig:
    llm_provider: str = "azure"
    model: str = "gpt-4o"
    temperature: float = 0.7

# Docker Model Runner (FREE local inference)
# Prerequisites: Docker Desktop 4.40+ with Model Runner enabled
#               docker desktop enable model-runner --tcp 12434
#               docker model pull ai/llama3.2
@dataclass
class DockerConfig:
    llm_provider: str = "docker"
    model: str = "ai/llama3.2"  # Or ai/qwen3, ai/gemma3
    temperature: float = 0.7

# Ollama (FREE local models)
# Prerequisites: Ollama running on port 11434
@dataclass
class OllamaConfig:
    llm_provider: str = "ollama"
    model: str = "llama3.2"
    temperature: float = 0.7

# Google Gemini (Cloud, multimodal)
# Prerequisites: export GOOGLE_API_KEY="your-api-key"
#               pip install kailash-kaizen[google]
@dataclass
class GoogleConfig:
    llm_provider: str = "google"  # Or "gemini" (alias)
    model: str = "gemini-2.0-flash"  # Or gemini-1.5-pro, gemini-1.5-flash
    temperature: float = 0.7
```

### Auto-Detection

Kaizen automatically detects available providers in this priority order:
1. OpenAI (if `OPENAI_API_KEY` set)
2. Azure (if `AZURE_AI_INFERENCE_ENDPOINT` set)
3. Anthropic (if `ANTHROPIC_API_KEY` set)
4. Google (if `GOOGLE_API_KEY` or `GEMINI_API_KEY` set)
5. Ollama (if running locally)
6. Docker Model Runner (if running locally)

Override with `KAIZEN_DEFAULT_PROVIDER` environment variable.

### Docker Model Runner Tool Calling

Tool calling support is model-dependent. Check capability:

```python
from kaizen.nodes.ai import DockerModelRunnerProvider

provider = DockerModelRunnerProvider()
if provider.supports_tools("ai/qwen3"):
    # Tool calling supported
    pass
```

### Google Gemini Provider

Supports chat, vision (multimodal), embeddings, and tool calling via the `google-genai` SDK:

```python
from kaizen.nodes.ai import GoogleGeminiProvider

provider = GoogleGeminiProvider()

# Chat completion
messages = [{"role": "user", "content": "What is 2+2?"}]
response = provider.chat(
    messages=messages,
    model="gemini-2.0-flash",
    generation_config={"temperature": 0.7, "max_tokens": 100}
)
print(response["content"])  # "4"

# Vision (multimodal) - pass base64-encoded images
import base64
with open("image.png", "rb") as f:
    image_b64 = base64.b64encode(f.read()).decode()

messages = [{
    "role": "user",
    "content": [
        {"type": "text", "text": "What's in this image?"},
        {"type": "image", "base64": image_b64, "media_type": "image/png"}
    ]
}]
response = provider.chat(messages=messages, model="gemini-2.0-flash")

# Embeddings (768-dimensional vectors)
texts = ["Hello world", "Machine learning"]
embeddings = provider.embed(texts=texts, model="text-embedding-004")

# Async support
response = await provider.chat_async(messages=messages, model="gemini-2.0-flash")
embeddings = await provider.embed_async(texts=texts, model="text-embedding-004")
```

**Tool-Capable Models**: `ai/qwen3`, `ai/llama3.3`, `ai/gemma3`

## 🏗️ BaseAgent Architecture

### The BaseAgent Pattern

All Kaizen agents follow the same unified architecture:

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from dataclasses import dataclass

# Step 1: Define Configuration (auto-extracted by BaseAgent)
@dataclass
class QAConfig:
    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.1
    max_tokens: int = 300
    # BaseAgent auto-extracts: llm_provider, model, temperature, max_tokens, provider_config

# Step 2: Define Signature (type-safe inputs/outputs)
class QASignature(Signature):
    """Answer questions accurately and concisely with confidence scoring."""
    question: str = InputField(desc="The question to answer")
    context: str = InputField(desc="Additional context if available", default="")

    answer: str = OutputField(desc="Clear, accurate answer")
    confidence: float = OutputField(desc="Confidence score 0.0-1.0")
    reasoning: str = OutputField(desc="Brief explanation of reasoning")

# Step 3: Extend BaseAgent
class SimpleQAAgent(BaseAgent):
    """Simple Q&A Agent using BaseAgent architecture."""

    def __init__(self, config: QAConfig):
        # BaseAgent auto-converts config → BaseAgentConfig
        super().__init__(config=config, signature=QASignature())
        self.qa_config = config

    def ask(self, question: str, context: str = "") -> dict:
        """
        Process a question and return structured answer.

        BaseAgent.run() provides:
        - Automatic logging (LoggingMixin)
        - Performance tracking (PerformanceMixin)
        - Error handling (ErrorHandlingMixin)
        - Memory management (if configured)
        """
        return self.run(question=question, context=context)
```

### What BaseAgent Provides

**Automatic Features** (inherited by all agents):
1. **Config Auto-Extraction**: Converts domain config → BaseAgentConfig
2. **Async Execution**: AsyncSingleShotStrategy for 2-3x performance improvement
3. **Error Handling**: Automatic retries, timeouts, graceful degradation
4. **Performance Tracking**: Built-in timing, token counting, cost tracking
5. **Structured Logging**: Comprehensive logging with context
6. **Memory Management**: Optional BufferMemory with session support
7. **A2A Integration**: Auto-generates Agent-to-Agent capability cards
8. **Workflow Generation**: `to_workflow()` for Core SDK integration

**Code Reduction:**
- Traditional agent: ~496 lines
- BaseAgent-based: ~65 lines
- **87% reduction** with more features

## 📚 Available Specialized Agents

### Implemented and Production-Ready

```python
from kaizen.agents import (
    # Single-Agent Patterns
    SimpleQAAgent,           # Question answering with confidence scoring
    ChainOfThoughtAgent,     # Step-by-step reasoning
    ReActAgent,              # Reasoning + action cycles
    RAGResearchAgent,        # Research with retrieval-augmented generation
    CodeGenerationAgent,     # Code generation and explanation
    MemoryAgent,             # Memory-enhanced conversations

    # Multi-Modal Agents
    VisionAgent,             # Image analysis (Ollama llava/bakllava + OpenAI GPT-4V)
    TranscriptionAgent,      # Audio transcription (Whisper)
)
```

### Usage Examples

**SimpleQAAgent - Question Answering:**
```python
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig

config = QAConfig(llm_provider="openai", model="gpt-4")
agent = SimpleQAAgent(config)
result = agent.ask("What is the capital of France?")
print(result["answer"])  # "Paris"
print(result["confidence"])  # 0.95
```

**ChainOfThoughtAgent - Step-by-Step Reasoning:**
```python
from kaizen.agents import ChainOfThoughtAgent
from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtConfig

config = ChainOfThoughtConfig(llm_provider="openai", model="gpt-4")
agent = ChainOfThoughtAgent(config)
result = agent.think("If John has 3 apples and Mary gives him 5 more, how many does he have?")
print(result["reasoning_steps"])  # ["Step 1: John starts with 3 apples", ...]
print(result["final_answer"])     # "8 apples"
```

**VisionAgent - Image Analysis:**
```python
from kaizen.agents import VisionAgent, VisionAgentConfig

# Ollama vision (free, local)
config = VisionAgentConfig(llm_provider="ollama", model="bakllava")
agent = VisionAgent(config=config)

result = agent.analyze(
    image="/path/to/receipt.jpg",
    question="What is the total amount?"
)
print(result['answer'])  # "$42.99"
```

**TranscriptionAgent - Audio Transcription:**
```python
from kaizen.agents import TranscriptionAgent, TranscriptionAgentConfig

config = TranscriptionAgentConfig()  # Uses Whisper by default
agent = TranscriptionAgent(config=config)

result = agent.transcribe(audio_path="/path/to/audio.mp3")
print(result['transcription'])  # Full text transcription
```

## 🎯 Multi-Modal Processing

### Vision Processing (Ollama + OpenAI)

```python
from kaizen.agents import VisionAgent, VisionAgentConfig

# Option 1: Ollama (free, local, requires Ollama installed)
ollama_config = VisionAgentConfig(
    llm_provider="ollama",
    model="bakllava"  # or "llava"
)
ollama_agent = VisionAgent(config=ollama_config)

# Option 2: OpenAI GPT-4V (paid API, higher quality)
openai_config = VisionAgentConfig(
    llm_provider="openai",
    model="gpt-4o"
)
openai_agent = VisionAgent(config=openai_config)

# Analyze image
result = ollama_agent.analyze(
    image="/path/to/invoice.jpg",
    question="Extract all line items and totals"
)
print(result['answer'])
```

### Audio Processing (Whisper)

```python
from kaizen.agents import TranscriptionAgent, TranscriptionAgentConfig

config = TranscriptionAgentConfig()
agent = TranscriptionAgent(config=config)

# Transcribe audio file
result = agent.transcribe(audio_path="/path/to/meeting.mp3")
print(result['transcription'])
print(result['duration'])
print(result['language'])
```

### Common Pitfalls - Multi-Modal API

```python
# ❌ WRONG: Using 'prompt' instead of 'question'
result = vision_agent.analyze(image=img, prompt="What is this?")

# ❌ WRONG: Using 'response' key instead of 'answer'
answer = result['response']

# ❌ WRONG: Passing base64 string instead of file path
result = vision_agent.analyze(image=base64_string, question="...")

# ✅ CORRECT: Use 'question' parameter and 'answer' key
result = vision_agent.analyze(image="/path/to/image.png", question="What is this?")
answer = result['answer']
```

## 🤝 Multi-Agent Coordination

### Google A2A Protocol Integration

Kaizen implements the Google Agent-to-Agent (A2A) protocol for semantic capability matching. **No hardcoded if/else logic** - agents automatically match tasks based on semantic similarity.

```python
from kaizen.orchestration.patterns import SupervisorWorkerPattern
from kaizen.agents import SimpleQAAgent, CodeGenerationAgent, RAGResearchAgent

# Create specialized worker agents
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

# Semantic task routing (eliminates 40-50% of manual selection logic)
result = pattern.execute_task("Analyze this codebase and suggest improvements")

# A2A automatically selects best worker based on semantic similarity
best_worker = pattern.supervisor.select_worker_for_task(
    task="Analyze sales data and create visualization",
    available_workers=[qa_agent, code_agent, research_agent],
    return_score=True
)
# Returns: {"worker": <RAGResearchAgent>, "score": 0.87}
```

### Available Coordination Patterns

1. **SupervisorWorkerPattern** - Task delegation with semantic matching ✅
2. **ConsensusPattern** - Group decision-making
3. **DebatePattern** - Adversarial reasoning
4. **SequentialPattern** - Step-by-step processing
5. **HandoffPattern** - Dynamic agent handoff

## 🛠️ Autonomous Tool Calling

### Overview

BaseAgent supports autonomous tool calling with built-in safety controls and approval workflows. Agents can discover, execute, and chain tools to accomplish complex tasks.

```python
from kaizen.core.base_agent import BaseAgent
# Tools auto-configured via MCP


# Enable tool calling

# 12 builtin tools enabled via MCP

agent = BaseAgent(
    config=config,
    signature=signature,
    tools="all"  # Enable 12 builtin tools via MCP
)
```

### 12 Builtin Tools

**File Operations (5 tools):**
- `read_file`, `write_file`, `delete_file`, `list_directory`, `file_exists`

**HTTP Requests (4 tools):**
- `http_get`, `http_post`, `http_put`, `http_delete`

**System Operations (1 tool):**
- `bash_command`

**Web Scraping (2 tools):**
- `fetch_url`, `extract_links`

### Tool Discovery and Execution

```python
# Discover available tools
tools = await agent.discover_tools(category="file", safe_only=True)

# Execute single tool (with approval workflow)
result = await agent.execute_tool(
    tool_name="read_file",
    params={"path": "/tmp/data.txt"}
)

if result.success and result.approved:
    print(f"Content: {result.result['content']}")

# Chain multiple tools
results = await agent.execute_tool_chain([
    {"tool_name": "read_file", "params": {"path": "input.txt"}},
    {"tool_name": "bash_command", "params": {"command": "wc -l input.txt"}},
    {"tool_name": "write_file", "params": {"path": "output.txt", "content": "..."}}
])
```

### Approval Workflows

Tools are classified by danger level:
- **SAFE**: Auto-approved (no side effects) - `list_directory`, `file_exists`
- **LOW**: Read-only operations - `read_file`, `http_get`
- **MEDIUM**: Data modification - `write_file`, `http_post`
- **HIGH**: Destructive operations - `delete_file`, `bash_command`

Non-SAFE tools require explicit approval via the Control Protocol.

## 🔄 Control Protocol

### Bidirectional Communication

The Control Protocol enables bidirectional communication between agents and clients for interactive workflows.

```python
from kaizen.core.autonomy.control import ControlProtocol
from kaizen.core.autonomy.control.transports import CLITransport

# Create protocol with CLI transport
protocol = ControlProtocol(CLITransport())

# Use with agent
agent = BaseAgent(
    config=config,
    signature=signature,
    tools="all"  # Enable 12 builtin tools via MCP
    control_protocol=protocol  # Enable bidirectional communication
)

# Start protocol
import anyio
async with anyio.create_task_group() as tg:
    await protocol.start(tg)

    # Agent can now ask questions during execution
    answer = await agent.ask_user_question(
        "Which environment?",
        ["dev", "staging", "production"]
    )

    # Request approval for dangerous operations
    approved = await agent.request_approval(
        "Delete old files?",
        {"files": ["old1.txt", "old2.txt"], "count": 2}
    )

    # Report progress
    await agent.report_progress("Processing files", percentage=50)
```

### Available Transports

- **CLITransport**: Interactive command-line interface
- **HTTPTransport (SSE)**: Server-sent events for web UIs
- **StdioTransport**: Standard I/O for MCP integration
- **MemoryTransport**: In-memory for testing

## 🎛️ Lifecycle Infrastructure

**Production-ready hooks, state management, and interrupts for enterprise agents.**

### Hooks - Event-Driven Monitoring

**Zero-code-change observability** - Add monitoring, tracing, and auditing without modifying agent logic.

```python
from kaizen.core.autonomy.hooks.builtin import LoggingHook, MetricsHook, AuditHook

# Every BaseAgent has a hook manager
agent = BaseAgent(config=config, signature=signature)

# Register builtin hooks (one line each!)
agent._hook_manager.register_hook(LoggingHook(log_level="INFO"))
agent._hook_manager.register_hook(MetricsHook())
agent._hook_manager.register_hook(AuditHook(audit_path="./audit"))

# Execute agent - hooks run automatically
result = agent.run(question="test")
```

**6 Production-Ready Hooks:**
- `LoggingHook`: Structured JSON logging for ELK Stack
- `MetricsHook`: Prometheus metrics with p50/p95/p99 percentiles
- `CostTrackingHook`: Budget tracking by tool/agent/specialist
- `PerformanceProfilerHook`: Latency profiling with percentiles
- `AuditHook`: Immutable audit trails (SOC2/GDPR/HIPAA)
- `TracingHook`: Distributed tracing (OpenTelemetry + Jaeger)

**Production Validated**: 281 tests passing (Phase 3 complete), <0.01ms overhead (p95), 100+ concurrent hooks supported.

**See**: [Hooks System Guide](docs/guides/hooks-system.md) for complete documentation.

### State - Persistent Checkpoints

```python
from kaizen.core.autonomy.state import StateManager, FilesystemStorage, AgentState

# Create state manager
storage = FilesystemStorage(base_path="./agent_state")
state_manager = StateManager(storage_backend=storage)

# Create checkpoint before risky operation
checkpoint_id = await state_manager.create_checkpoint(
    agent_id="my_agent",
    description="Before processing"
)

# Execute agent
result = agent.run(question="test")

# Save state
state = AgentState(
    agent_id="my_agent",
    conversation_history=agent.get_history(),
    metadata={"result": result}
)
await state_manager.save_state(state)

# Restore on error
await state_manager.restore_checkpoint(checkpoint_id)
```

**Features:**
- Automatic checkpointing
- Version history tracking
- Multiple storage backends (Filesystem, Redis, PostgreSQL, S3)
- Metadata attachment
- TTL support

### Interrupts - Graceful Control

```python
from kaizen.core.autonomy.interrupts import InterruptSignal

# Request interruption
agent._interrupt_manager.request_interrupt(
    signal=InterruptSignal.USER_REQUESTED,
    reason="Awaiting approval"
)

# Check if interrupted
if agent._interrupt_manager.is_interrupted():
    # Save state and pause
    await state_manager.save_state(current_state)
    return {"status": "paused", "resume_token": "xyz"}

# Resume execution
agent._interrupt_manager.clear_interrupt()
```

**6 Interrupt Signals:**
- `USER_REQUESTED`: Manual pause
- `RATE_LIMIT`: API rate limit hit
- `BUDGET_EXCEEDED`: Cost budget exceeded
- `TIMEOUT`: Operation timeout
- `SHUTDOWN`: Graceful shutdown
- `CUSTOM`: User-defined signals

## 🔐 Permission System

**Policy-based access control with budget enforcement for enterprise security.**

### Basic Usage

```python
from kaizen.core.autonomy.permissions import ExecutionContext, PermissionRule, PermissionType, PermissionMode

# Create execution context
context = ExecutionContext(
    mode=PermissionMode.DEFAULT,
    budget_limit=50.0,  # $50 maximum
    allowed_tools={"read_file", "http_get"},
    denied_tools={"delete_file", "bash_command"}
)

# Define permission rules
rules = [
    # Deny destructive operations
    PermissionRule(
        pattern="(delete|drop|truncate)_.*",
        permission_type=PermissionType.DENY,
        reason="Destructive operations not allowed",
        priority=100
    ),
    # Ask for write operations
    PermissionRule(
        pattern="(write|create|update)_.*",
        permission_type=PermissionType.ASK,
        reason="Write operations require approval",
        priority=50
    ),
    # Allow read operations
    PermissionRule(
        pattern="(read|get|list)_.*",
        permission_type=PermissionType.ALLOW,
        reason="Read operations are safe",
        priority=10
    )
]

# Check permissions
if context.can_use_tool("read_file"):
    result = await agent.execute_tool("read_file", {"path": "data.txt"})
    context.record_tool_usage("read_file", cost=0.001)

# Check budget
if context.has_budget():
    # Proceed with operation
    pass
else:
    raise BudgetExceededError("Cost limit reached")
```

### Permission Modes
- **DEFAULT**: Standard permission checks (production)
- **ACCEPT_EDITS**: Auto-approve edit operations (development)
- **PLAN**: Planning mode, no execution (dry-run)
- **BYPASS**: Bypass all checks (admin mode)

### Permission Types
- **ALLOW**: Auto-approve execution
- **DENY**: Block execution completely
- **ASK**: Request user approval

### Enterprise Features
- **Budget Tracking**: Cost limits and usage monitoring
- **Pattern Matching**: Regex-based tool name matching
- **Multi-Agent Isolation**: Per-agent permission contexts
- **Audit Trail**: Track all permission decisions
- **Compliance**: SOC2, HIPAA, PCI-DSS ready

## 🧠 Memory & Learning System

**Production-ready memory with learning capabilities for conversational agents.**

### 3 Memory Types

```python
from kaizen.memory import ShortTermMemory, LongTermMemory, SemanticMemory
from kaizen.memory.storage import SQLiteStorage

# Short-term memory (session-scoped)
short_term = ShortTermMemory(max_entries=100, ttl_seconds=3600)
short_term.add(content={"question": "What is AI?"}, importance=0.8)

# Long-term memory (persistent)
storage = SQLiteStorage(db_path="./agent_memory.db")
long_term = LongTermMemory(storage_backend=storage)
long_term.add(content={"user_name": "Alice"}, importance=0.9)

# Semantic search
similar = long_term.search_similar(query="user preferences", limit=5, min_similarity=0.7)
```

### 4 Learning Mechanisms

```python
from kaizen.memory.learning import PatternRecognition, PreferenceLearning, ErrorCorrection

# Pattern recognition (detect FAQs)
pattern_learner = PatternRecognition(memory=long_term)
faqs = pattern_learner.detect_frequent_patterns(min_occurrences=3, time_window_days=7)

# Preference learning
pref_learner = PreferenceLearning(memory=long_term)
user_prefs = pref_learner.learn_preferences(user_id="alice", min_confidence=0.7)

# Error correction (learn from mistakes)
error_learner = ErrorCorrection(memory=long_term)
error_learner.record_error(
    error_type="invalid_tool_call",
    context={"tool": "read_file", "error": "FileNotFoundError"},
    correction="Check file existence before reading"
)
```

### BaseAgent Integration

```python
from kaizen.core.base_agent import BaseAgent

agent = BaseAgent(config=config, signature=signature)
agent._memory = long_term  # Attach memory system

# Agent now remembers conversations, learns patterns, avoids past errors
result = agent.run(question="What's my communication style?")
```

**Performance (Production validated):**
- <50ms retrieval (p95), <100ms storage (p95)
- 10,000+ entries per agent (SQLite), millions (PostgreSQL)
- 281 tests passing (Phase 3 complete)

**Use Cases:** Conversational agents, customer support, research agents, code generation, multi-agent systems

## 📄 Document Extraction & RAG

**Production-ready document extraction with RAG-optimized chunking.**

### 3 Provider Options

```python
from kaizen.agents.multi_modal import DocumentExtractionAgent, DocumentExtractionConfig

# FREE configuration (Ollama vision - $0.00 cost)
config = DocumentExtractionConfig(
    provider="ollama_vision",
    chunk_for_rag=True,
    chunk_size=512,
    overlap=50,
    extract_tables=True
)

agent = DocumentExtractionAgent(config=config)

# Extract document with RAG chunking
result = agent.extract(
    file_path="report.pdf",
    extract_tables=True,
    chunk_for_rag=True
)

# Access RAG-ready chunks with page citations
for chunk in result['chunks']:
    print(f"Page {chunk['page']}: {chunk['text'][:100]}...")
```

### Vector Store Integration

```python
from kaizen.rag import VectorStore

vector_store = VectorStore()
for chunk in result['chunks']:
    vector_store.add(
        text=chunk['text'],
        metadata={"source": "document.pdf", "page": chunk['page']},
        embedding=generate_embedding(chunk['text'])
    )

# RAG query with source attribution
query = "What are the key findings?"
relevant_chunks = vector_store.search(query, limit=5)

for chunk in relevant_chunks:
    print(f"Source: {chunk['metadata']['source']}, Page: {chunk['metadata']['page']}")
    print(f"Content: {chunk['text']}\n")
```

### Provider Comparison

| Provider      | Speed | Accuracy | Cost (per page) | Best For                     |
|---------------|-------|----------|-----------------|------------------------------|
| Ollama        | 2-4s  | 70-80%   | $0.00           | Unlimited processing, dev    |
| OpenAI Vision | 1-2s  | 85-90%   | ~$0.01          | Production, good accuracy    |
| Landing AI    | 2-3s  | 95%+     | ~$0.05          | Mission-critical, max accuracy |

**Production Validated:**
- 281 tests passing (Phase 3 complete)
- Real infrastructure testing (NO MOCKING)
- Ollama: $0.00 cost for unlimited processing
- RAG chunking with page citations for source attribution

**Use Cases:** RAG systems, enterprise document search, research paper analysis, compliance processing, invoice/receipt extraction, legal document analysis

## 🔧 Creating Custom Agents

### Basic Custom Agent

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from dataclasses import dataclass

# 1. Define your configuration
@dataclass
class SentimentConfig:
    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.2
    categories: list = None  # Custom field

    def __post_init__(self):
        if self.categories is None:
            self.categories = ["positive", "negative", "neutral"]

# 2. Define your signature
class SentimentSignature(Signature):
    text: str = InputField(desc="Text to analyze")

    sentiment: str = OutputField(desc="Sentiment category")
    confidence: float = OutputField(desc="Confidence 0.0-1.0")
    explanation: str = OutputField(desc="Brief explanation")

# 3. Extend BaseAgent
class SentimentAgent(BaseAgent):
    def __init__(self, config: SentimentConfig):
        super().__init__(config=config, signature=SentimentSignature())
        self.sentiment_config = config

    def analyze(self, text: str) -> dict:
        """Analyze sentiment with domain-specific logic."""
        # BaseAgent.run() handles everything else
        result = self.run(text=text)

        # Add custom validation
        if result["sentiment"] not in self.sentiment_config.categories:
            result["warning"] = f"Unexpected category: {result['sentiment']}"

        return result

# Usage
config = SentimentConfig(llm_provider="openai", model="gpt-4")
agent = SentimentAgent(config)
result = agent.analyze("This product is amazing!")
print(result["sentiment"])  # "positive"
print(result["confidence"])  # 0.92
```

### Advanced: Custom Strategy

```python
from kaizen.strategies.base import Strategy
from typing import Dict, Any

class CustomStrategy(Strategy):
    """Custom execution strategy for specialized workflows."""

    async def execute(self, signature, inputs: Dict[str, Any], config) -> Dict[str, Any]:
        # Custom pre-processing
        processed_inputs = self.preprocess(inputs)

        # Execute with LLM
        result = await self.llm_call(signature, processed_inputs, config)

        # Custom post-processing
        return self.postprocess(result)

# Use in custom agent
class AdvancedAgent(BaseAgent):
    def __init__(self, config):
        super().__init__(
            config=config,
            signature=MySignature(),
            strategy=CustomStrategy()  # Use custom strategy
        )
```

## 🔌 Integration Patterns

### Integration with DataFlow

```python
from dataflow import DataFlow
from kaizen.agents import SimpleQAAgent, QAConfig
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# DataFlow for database operations
db = DataFlow()

@db.model
class QASession:
    question: str
    answer: str
    confidence: float
    timestamp: str

# Kaizen for AI processing
agent = SimpleQAAgent(QAConfig(llm_provider="openai", model="gpt-4"))
result = agent.ask("What is the capital of France?")

# Store in database via DataFlow nodes
workflow = WorkflowBuilder()
workflow.add_node("QASessionCreateNode", "store", {
    "question": "What is the capital of France?",
    "answer": result["answer"],
    "confidence": result["confidence"],
    "timestamp": "2025-01-17T10:30:00"
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Integration with Nexus

```python
from nexus import Nexus
from kaizen.agents import SimpleQAAgent, QAConfig

# Create Nexus platform
nexus = Nexus(
    title="AI Q&A Platform",
    enable_api=True,
    enable_cli=True,
    enable_mcp=True
)

# Deploy Kaizen agent via Nexus
agent = SimpleQAAgent(QAConfig())
agent_workflow = agent.to_workflow()
nexus.register("qa_agent", agent_workflow.build())

# Agent now available on all channels:
# - REST API: POST /workflows/qa_agent
# - CLI: nexus run qa_agent --question "What is AI?"
# - MCP: qa_agent tool for AI assistants like Claude
```

## 🧪 Testing

### 3-Tier Testing Strategy

Kaizen uses a rigorous 3-tier testing approach with **NO MOCKING** in Tiers 2-3:

1. **Tier 1 (Unit)**: Fast, mocked LLM providers (~450+ tests)
2. **Tier 2 (Integration)**: Real Ollama inference (local, free)
3. **Tier 3 (E2E)**: Real OpenAI inference (paid API, budget-controlled)

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

### Testing Custom Agents

```python
import pytest
from kaizen.agents import SimpleQAAgent, QAConfig

def test_simple_qa_agent():
    """Test basic Q&A functionality."""
    config = QAConfig(llm_provider="mock")  # Use mock provider for unit tests
    agent = SimpleQAAgent(config)

    result = agent.ask("What is 2+2?")

    assert "answer" in result
    assert "confidence" in result
    assert isinstance(result["confidence"], float)
    assert 0 <= result["confidence"] <= 1

def test_memory_enabled_agent():
    """Test memory continuity across sessions."""
    config = QAConfig(max_turns=10)  # Enable memory
    agent = SimpleQAAgent(config)

    # First interaction
    result1 = agent.ask("My name is Alice", session_id="test123")

    # Memory recall
    result2 = agent.ask("What's my name?", session_id="test123")

    assert "alice" in result2["answer"].lower()
```

## 📦 Production Deployment

### Environment Configuration

```bash
# Required API Keys (.env file)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Optional Configuration
KAIZEN_LOG_LEVEL=INFO
KAIZEN_PERFORMANCE_TRACKING=true
KAIZEN_ERROR_HANDLING=true
```

### Docker Deployment

```dockerfile
FROM python:3.11-slim

# Install Kaizen
RUN pip install kailash-kaizen

# Copy application
COPY app.py .
COPY .env .

# Run application
CMD ["python", "app.py"]
```

### Production Agent Configuration

```python
from kaizen.agents import SimpleQAAgent, QAConfig

# Production configuration with enterprise features
config = QAConfig(
    llm_provider="openai",
    model="gpt-4",
    temperature=0.1,  # Lower for consistency
    max_tokens=500,
    timeout=30,  # Request timeout
    retry_attempts=3,  # Retry on failures
    max_turns=50,  # Enable memory with limit
    min_confidence_threshold=0.7  # Quality gate
)

agent = SimpleQAAgent(config)
```

## 📊 Performance

### BaseAgent Performance Improvements

- **Async Execution**: 2-3x faster than sync execution
- **Lazy Loading**: <100ms framework initialization
- **Code Reduction**: 87% less code vs traditional agents
- **Auto-Optimization**: Strategy-based execution optimization

### Multi-Modal Performance

- **Vision (Ollama)**: ~2-5 seconds per image (local, free)
- **Vision (OpenAI)**: ~1-2 seconds per image (paid, higher quality)
- **Audio (Whisper)**: ~0.5x real-time (1 min audio → ~30 sec processing)

## 📚 Examples

### Complete Examples Repository

Kaizen includes 35+ working examples across 8 categories:

```
examples/
├── 1-single-agent/        # 10 basic patterns
│   ├── simple-qa/
│   ├── chain-of-thought/
│   ├── react-agent/
│   └── ...
├── 2-multi-agent/         # 6 coordination patterns
│   ├── supervisor-worker/
│   ├── consensus-building/
│   └── ...
├── 3-enterprise-workflows/ # 5 production patterns
│   ├── customer-service/
│   ├── document-analysis/
│   └── ...
├── 4-advanced-rag/        # 5 RAG techniques
│   ├── agentic-rag/
│   ├── graph-rag/
│   └── ...
├── 5-mcp-integration/     # 5 MCP patterns
├── 8-multi-modal/         # Vision/audio examples
└── README.md              # Examples overview
```

**Location**: `./repos/projects/kailash_python_sdk/apps/kailash-kaizen/examples/`

## ⚠️ Common Mistakes

### 1. Missing .env Configuration
```python
# ❌ WRONG: Not loading environment variables
from kaizen.agents import SimpleQAAgent, QAConfig
agent = SimpleQAAgent(QAConfig(llm_provider="openai"))  # Fails!

# ✅ CORRECT: Load .env first
from dotenv import load_dotenv
load_dotenv()
agent = SimpleQAAgent(QAConfig(llm_provider="openai"))  # Works!
```

### 2. Wrong Vision Agent API
```python
# ❌ WRONG: Using 'prompt' and 'response'
result = vision_agent.analyze(image=img, prompt="What is this?")
answer = result['response']

# ✅ CORRECT: Use 'question' and 'answer'
result = vision_agent.analyze(image="/path/to/image.png", question="What is this?")
answer = result['answer']
```

### 3. Using BaseAgentConfig Directly
```python
# ❌ WRONG: Using BaseAgentConfig directly
from kaizen.core.config import BaseAgentConfig
config = BaseAgentConfig(model="gpt-4")  # Don't do this!

# ✅ CORRECT: Use domain config (auto-converted)
from kaizen.agents.specialized.simple_qa import QAConfig
config = QAConfig(model="gpt-4")
agent = SimpleQAAgent(config)  # Auto-extraction happens here
```

## 🔗 Additional Resources

### Documentation
- **[CLAUDE.md](CLAUDE.md)** - Quick reference for Claude Code
- **[Examples](../../../apps/kailash-kaizen/examples/)** - 35+ working implementations
- **[Core SDK](../../2-core-concepts/)** - Foundation patterns
- **[DataFlow](../dataflow/)** - Database framework integration
- **[Nexus](../nexus/)** - Multi-channel platform integration

### Guides
- **[Installation Guide](docs/getting-started/installation.md)** - Setup and dependencies
- **[Quickstart Tutorial](docs/getting-started/quickstart.md)** - Your first agent
- **[Signature Programming](docs/guides/signature-programming.md)** - Type-safe I/O
- **[BaseAgent Architecture](docs/guides/baseagent-architecture.md)** - Unified system
- **[Multi-Modal Processing](docs/guides/multi-modal.md)** - Vision and audio
- **[Multi-Agent Coordination](docs/guides/multi-agent.md)** - A2A protocol

### Reference
- **[API Reference](docs/reference/api-reference.md)** - Complete API docs
- **[Configuration Guide](docs/reference/configuration.md)** - All config options
- **[Troubleshooting](docs/reference/troubleshooting.md)** - Common issues

### Community
- **[GitHub Repository](https://github.com/terrene-foundation/kailash-py)** - Source code and issues
- **[Kailash SDK Documentation](../../../CLAUDE.md)** - Main SDK documentation

---

**Ready to get started?** Begin with our **[Quickstart Tutorial](docs/getting-started/quickstart.md)** or explore **[Working Examples](../../../apps/kailash-kaizen/examples/)**.
