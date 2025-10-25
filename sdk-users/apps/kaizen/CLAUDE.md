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

**Implemented and Production-Ready (v0.5.0):**
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

**Autonomous tool execution with approval workflows - Universal Integration (All 25 Agents):**
```python
from kaizen.core.base_agent import BaseAgent
from kaizen.tools import ToolRegistry
from kaizen.tools.builtin import register_builtin_tools

# Setup tool registry
registry = ToolRegistry()
register_builtin_tools(registry)  # 12 builtin tools

# Works with ALL 25 agents (ADR-016 complete)
agent = BaseAgent(
    config=config,
    signature=signature,
    tool_registry=registry,  # Enable tool calling
    mcp_servers=mcp_servers  # Optional MCP integration
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

**Universal Support**: All 25 agents (autonomous, single-shot, coordination) now support tool_registry and mcp_servers parameters (100% backward compatible)

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

### Observability & Performance Monitoring (NEW in v0.5.0)

**Production-ready observability with zero overhead (-0.06%):**
```python
from kaizen.core.base_agent import BaseAgent

# Create agent
agent = BaseAgent(config=config, signature=signature)

# Enable full observability stack (one line!)
agent.enable_observability(
    service_name="my-agent",      # Service name for all systems
    enable_metrics=True,          # Prometheus metrics
    enable_logging=True,          # Structured JSON logs
    enable_tracing=True,          # Distributed tracing
    enable_audit=True,            # Compliance audit trails
)

# All operations now tracked with zero overhead
result = agent.run(question="test")
```

**Complete Monitoring Stack:**
- **Distributed Tracing**: OpenTelemetry + Jaeger (UI: http://localhost:16686)
- **Metrics Collection**: Prometheus with p50/p95/p99 percentiles (UI: http://localhost:9090)
- **Structured Logging**: JSON logs for ELK Stack (UI: http://localhost:5601)
- **Audit Trails**: Immutable JSONL for SOC2/GDPR/HIPAA compliance
- **Grafana Dashboards**: 10+ pre-built dashboards (UI: http://localhost:3000)

**Production Validated (v0.5.0 Release):**
- -0.06% overhead (essentially zero, tested with 100 real OpenAI API calls)
- 0.57ms p95 audit latency (<10ms target, 17.5x margin)
- Validated with real infrastructure (NO MOCKING in Tiers 2-3 tests)

**Start Observability Stack:**
```bash
cd docs/observability
docker-compose up -d  # Starts Jaeger, Prometheus, Grafana, ELK Stack
```

### Lifecycle Infrastructure (NEW in v0.5.0)

**Production-ready hooks, state management, and interrupts for enterprise agents:**

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.autonomy.hooks.builtin import LoggingHook, MetricsHook
from kaizen.core.autonomy.state import StateManager, FilesystemStorage
from kaizen.core.autonomy.interrupts import InterruptSignal

# Every BaseAgent has lifecycle infrastructure built-in
agent = BaseAgent(config=config, signature=signature)

# 1. Hooks - Event-driven monitoring
agent._hook_manager.register_hook(LoggingHook(log_level="INFO"))
agent._hook_manager.register_hook(MetricsHook())

# 2. State - Persistent checkpoints
storage = FilesystemStorage(base_path="./agent_state")
state_manager = StateManager(storage_backend=storage)

# Create checkpoint before risky operation
checkpoint_id = await state_manager.create_checkpoint(
    agent_id=agent.agent_id,
    description="Before processing"
)

# Execute agent
result = agent.run(question="test")

# Save state
await state_manager.save_state(current_state)

# 3. Interrupts - Graceful control
agent._interrupt_manager.request_interrupt(
    signal=InterruptSignal.USER_REQUESTED,
    reason="Awaiting approval"
)

if agent._interrupt_manager.is_interrupted():
    # Save and pause
    await state_manager.save_state(current_state)
```

**Key Components:**
- **6 Builtin Hooks**: LoggingHook, MetricsHook, CostTrackingHook, PerformanceProfilerHook, AuditHook, TracingHook
- **4 Storage Backends**: Filesystem, Redis, PostgreSQL, S3
- **6 Interrupt Signals**: USER_REQUESTED, RATE_LIMIT, BUDGET_EXCEEDED, TIMEOUT, SHUTDOWN, CUSTOM

### Permission System (NEW in v0.5.0+)

**Policy-based access control with budget enforcement:**

```python
from kaizen.core.autonomy.permissions import ExecutionContext, PermissionRule, PermissionType, PermissionMode

# Create execution context with budget
context = ExecutionContext(
    mode=PermissionMode.DEFAULT,
    budget_limit=50.0,  # $50 maximum
    allowed_tools={"read_file", "http_get"},
    denied_tools={"delete_file"}
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

# Check permissions before tool execution
if context.can_use_tool("read_file"):
    result = await agent.execute_tool("read_file", {"path": "data.txt"})
    context.record_tool_usage("read_file", cost=0.001)

# Check budget
if context.has_budget():
    # Proceed with operation
    pass
```

**Features:**
- **4 Permission Modes**: DEFAULT, ACCEPT_EDITS, PLAN, BYPASS
- **3 Permission Types**: ALLOW, DENY, ASK
- **Budget Tracking**: Cost limits and usage monitoring
- **Pattern Matching**: Regex-based tool name matching
- **Multi-Agent Isolation**: Per-agent permission contexts

### Memory & Learning System (NEW in v0.5.0)

**Production-ready memory with learning capabilities for conversational agents:**

```python
from kaizen.memory import ShortTermMemory, LongTermMemory, SemanticMemory
from kaizen.memory.storage import SQLiteStorage, FileStorage, PostgreSQLStorage
from kaizen.memory.learning import PatternRecognition, PreferenceLearning, ErrorCorrection

# 1. Short-term memory (session-scoped, in-memory)
short_term = ShortTermMemory(max_entries=100, ttl_seconds=3600)
short_term.add(
    content={"question": "What is AI?", "answer": "..."},
    importance=0.8,
    tags=["qa", "technical"]
)

# 2. Long-term memory (persistent with SQLite)
storage = SQLiteStorage(db_path="./agent_memory.db")
long_term = LongTermMemory(storage_backend=storage)
long_term.add(
    content={"user_name": "Alice", "preferences": {"style": "formal"}},
    importance=0.9,
    tags=["user_profile"]
)

# 3. Semantic search (similarity-based retrieval)
similar_memories = long_term.search_similar(
    query="user preferences",
    limit=5,
    min_similarity=0.7
)

# 4. Pattern recognition (detect FAQs)
pattern_learner = PatternRecognition(memory=long_term)
faqs = pattern_learner.detect_frequent_patterns(
    min_occurrences=3,
    time_window_days=7
)

# 5. Preference learning
pref_learner = PreferenceLearning(memory=long_term)
user_prefs = pref_learner.learn_preferences(
    user_id="alice",
    min_confidence=0.7
)

# 6. Error correction (learn from mistakes)
error_learner = ErrorCorrection(memory=long_term)
error_learner.record_error(
    error_type="invalid_tool_call",
    context={"tool": "read_file", "error": "FileNotFoundError"},
    correction="Check file existence before reading"
)

# 7. BaseAgent integration
from kaizen.core.base_agent import BaseAgent

agent = BaseAgent(config=config, signature=signature)
agent._memory = long_term  # Attach memory system

# Agent can now remember conversations, learn patterns, avoid past errors
result = agent.run(question="What's my communication style?")
# Returns: "Based on your preferences, you prefer formal communication"
```

**3 Memory Types:**
- **ShortTermMemory**: Session-scoped, in-memory, fast retrieval (<10ms)
- **LongTermMemory**: Persistent, SQLite/File/PostgreSQL backends, semantic search
- **SemanticMemory**: Vector-based similarity search with embeddings

**3 Storage Backends:**
- **SQLiteStorage**: Local file-based, 10,000+ entries per agent
- **FileStorage**: JSONL append-only, portable, audit-friendly
- **PostgreSQLStorage**: Enterprise scale, millions of entries, distributed

**4 Learning Mechanisms:**
- **PatternRecognition**: Detect FAQs, common workflows, repetitive tasks
- **PreferenceLearning**: Learn user preferences from interactions
- **ErrorCorrection**: Record errors and corrections to avoid repeat mistakes
- **AdaptiveLearning**: Adjust strategies based on success rates

**Performance (v0.5.0 validated):**
- <50ms retrieval (p95)
- <100ms storage (p95)
- 10,000+ entries per agent (SQLite)
- Millions of entries (PostgreSQL)

**Use Cases:**
- Conversational agents with context continuity
- Customer support bots with preference learning
- Research agents that learn from feedback
- Code generation agents that avoid past errors
- Multi-agent systems with shared knowledge

### Document Extraction & RAG (NEW in v0.5.0)

**Production-ready document extraction with RAG-optimized chunking:**

```python
from kaizen.agents.multi_modal import DocumentExtractionAgent, DocumentExtractionConfig

# 1. FREE configuration (Ollama vision)
config = DocumentExtractionConfig(
    provider="ollama_vision",  # $0.00 cost
    chunk_for_rag=True,        # Enable RAG chunking
    chunk_size=512,            # Tokens per chunk
    overlap=50,                # Overlap for context continuity
    extract_tables=True        # Extract table data
)

agent = DocumentExtractionAgent(config=config)

# 2. Extract document with RAG chunking
result = agent.extract(
    file_path="report.pdf",
    extract_tables=True,
    chunk_for_rag=True
)

# 3. Access RAG-ready chunks with page citations
for chunk in result['chunks']:
    print(f"Page {chunk['page']}: {chunk['text'][:100]}...")
    # Each chunk has: text, page, start_idx, end_idx, metadata

# 4. Vector store integration
from kaizen.rag import VectorStore

vector_store = VectorStore()
for chunk in result['chunks']:
    vector_store.add(
        text=chunk['text'],
        metadata={
            "source": "document.pdf",
            "page": chunk['page'],
            "doc_id": "doc123"
        },
        embedding=generate_embedding(chunk['text'])  # Your embedding function
    )

# 5. RAG query with source attribution
query = "What are the key findings?"
relevant_chunks = vector_store.search(query, limit=5)

for chunk in relevant_chunks:
    print(f"Source: {chunk['metadata']['source']}, Page: {chunk['metadata']['page']}")
    print(f"Content: {chunk['text']}\n")

# 6. Batch processing for multiple documents
documents = ["doc1.pdf", "doc2.pdf", "doc3.pdf"]
batch_results = agent.extract_batch(
    file_paths=documents,
    chunk_for_rag=True,
    max_workers=3  # Parallel processing
)
```

**3 Provider Options:**

| Provider      | Speed | Accuracy | Cost (per page) | Best For                     |
|---------------|-------|----------|-----------------|------------------------------|
| Ollama        | 2-4s  | 70-80%   | $0.00           | Unlimited processing, dev    |
| OpenAI Vision | 1-2s  | 85-90%   | ~$0.01          | Production, good accuracy    |
| Landing AI    | 2-3s  | 95%+     | ~$0.05          | Mission-critical, max accuracy |

**RAG Optimization Features:**
- **Chunking**: Configurable size (default 512 tokens) with overlap
- **Page Citations**: Every chunk tracks source page for attribution
- **Table Extraction**: Structured table data with bounding boxes
- **Metadata Preservation**: Original formatting, fonts, positions
- **Cost Control**: Prefer-free mode tries Ollama first, falls back to paid

**Production Validated (v0.5.0):**
- 201 tests passing (149 unit + 34 integration + 18 E2E)
- Real infrastructure testing (NO MOCKING)
- Ollama: $0.00 cost for unlimited processing
- OpenAI: Budget-controlled, accurate
- Landing AI: Mission-critical accuracy (95%+)

**Use Cases:**
- RAG systems with source attribution
- Enterprise document search
- Research paper analysis
- Compliance document processing
- Invoice/receipt extraction
- Legal document analysis

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
- **[BaseAgent Architecture](docs/guides/baseagent-architecture.md)** - Unified agent system with strategies, memory, tools
- **[Multi-Agent Coordination](docs/guides/multi-agent-coordination.md)** - Google A2A protocol patterns
- **[Integration Patterns](docs/guides/integration-patterns.md)** - DataFlow, Nexus, MCP integration
- **[Control Protocol Tutorial](docs/guides/control-protocol-tutorial.md)** - CLI → Web migration guide
- **[Custom Transports](docs/guides/custom-transports.md)** - Build custom transport layers
- **[Migrating to Control Protocol](docs/guides/migrating-to-control-protocol.md)** - Migration guide
- **[Ollama Quickstart](docs/guides/ollama-quickstart.md)** - Local LLM setup

### Reference
- **[API Reference](docs/reference/api-reference.md)** - Complete API documentation
- **[Control Protocol API](docs/reference/control-protocol-api.md)** - Bidirectional communication API
- **[Multi-Modal API](docs/reference/multi-modal-api-reference.md)** - Vision, audio APIs with common pitfalls
- **[Memory Patterns Guide](docs/reference/memory-patterns-guide.md)** - Memory usage patterns
- **[Strategy Selection Guide](docs/reference/strategy-selection-guide.md)** - When to use which strategy
- **[Configuration Guide](docs/reference/configuration.md)** - Environment configuration
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
   - SupervisorWorkerPattern with semantic matching (production-ready)
   - 4 additional patterns: Consensus, Debate, Sequential, Handoff
   - Automatic capability discovery, no hardcoded selection

5. **Observability Stack (v0.5.0)** (`src/kaizen/core/autonomy/observability/`)
   - Distributed tracing: OpenTelemetry + Jaeger
   - Metrics collection: Prometheus with percentiles
   - Structured logging: JSON for ELK Stack
   - Audit trails: Immutable JSONL for compliance
   - Production-validated: -0.06% overhead, zero impact

6. **Lifecycle Infrastructure (v0.5.0)** (`src/kaizen/core/autonomy/`)
   - Hooks: Event-driven monitoring (6 builtin hooks)
   - State: Persistent checkpoints with pluggable storage
   - Interrupts: Graceful execution control (6 signal types)
   - Thread-safe, composable, extensible

7. **Permission System (v0.5.0+)** (`src/kaizen/core/autonomy/permissions/`)
   - ExecutionContext: Thread-safe runtime state
   - PermissionRule: Pattern-based access control
   - Budget enforcement: Cost tracking and limits
   - Enterprise security: RBAC, compliance, multi-tenant isolation

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
