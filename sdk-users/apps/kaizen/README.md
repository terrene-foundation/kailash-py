# Kailash Kaizen - Trust-First AI Agent Framework

**Version: 1.2.1** | Built on [Kailash Core SDK](https://github.com/terrene-foundation/kailash-py) | `pip install kailash-kaizen`

Kaizen is a **signature-based AI agent framework** with built-in trust, multi-modal processing, multi-agent coordination, and enterprise observability. Agents define type-safe Signatures for inputs and outputs, extend a unified BaseAgent architecture, and inherit production-grade features -- error handling, logging, performance tracking, memory management, and cryptographic trust chains -- automatically.

```python
import os
from dotenv import load_dotenv
load_dotenv()

from kaizen.api import Agent

model = os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o")
agent = Agent(model=model)
result = await agent.run("What is quantum computing?")
```

## Installation

```bash
pip install kailash-kaizen
```

```python
# Unified Agent API (v1.0.0+)
from kaizen.api import Agent

# Or the full BaseAgent pattern
from kaizen.core.base_agent import BaseAgent
```

## Quick Start

### Unified Agent API

```python
import os
from dotenv import load_dotenv
load_dotenv()

from kaizen.api import Agent

# Read model from environment -- never hardcode
model = os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o")

# Simple usage
agent = Agent(model=model)
result = await agent.run("What is IRP?")

# Autonomous mode with memory
agent = Agent(
    model=model,
    execution_mode="autonomous",
    memory="session",
    tool_access="constrained",
)
```

### BaseAgent Pattern (Full Control)

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from dataclasses import dataclass
import os
from dotenv import load_dotenv
load_dotenv()

@dataclass
class QAConfig:
    llm_provider: str = "openai"
    model: str = os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o")
    temperature: float = 0.7

class QASignature(Signature):
    """Answer questions accurately with confidence scoring."""
    question: str = InputField(desc="The question to answer")
    answer: str = OutputField(desc="Clear, accurate answer")
    confidence: float = OutputField(desc="Confidence score 0.0-1.0")

class QAAgent(BaseAgent):
    def __init__(self, config: QAConfig):
        super().__init__(config=config, signature=QASignature())

    def ask(self, question: str) -> dict:
        return self.run(question=question)

agent = QAAgent(QAConfig())
result = agent.ask("What is the capital of France?")
print(result["answer"])       # "Paris"
print(result["confidence"])   # 0.95
```

BaseAgent provides: config auto-extraction, async execution, error handling with retries, performance tracking, structured logging, optional memory management, A2A capability card generation, and workflow conversion via `to_workflow()`.

## Part of the Kailash Ecosystem

Kaizen is one of three frameworks built on the [Kailash Core SDK](https://github.com/terrene-foundation/kailash-py), each addressing a different layer of application development:

| Framework                                                           | Purpose                              | Install                        |
| ------------------------------------------------------------------- | ------------------------------------ | ------------------------------ |
| **[DataFlow](https://github.com/terrene-foundation/kailash-dataflow)** | Workflow-native database operations  | `pip install kailash-dataflow` |
| **[Nexus](https://github.com/terrene-foundation/kailash-nexus)**       | Multi-channel platform (API/CLI/MCP) | `pip install kailash-nexus`    |
| **Kaizen** (this)                                                   | AI agent framework with trust        | `pip install kailash-kaizen`   |

All three frameworks share the same workflow execution model: `runtime.execute(workflow.build())`. Kaizen agents can be converted to workflows via `agent.to_workflow()` and deployed through Nexus to reach users via API, CLI, or MCP. Kaizen agents can use DataFlow for persistent storage of conversation history, agent state, and knowledge bases.

**CARE/EATP Trust Framework**: Kaizen is the primary home of the CARE (Context, Action, Reasoning, Evidence) and EATP (Enterprise Agent Trust Protocol) trust frameworks. These provide:

- **Cryptographic trust chains**: Linked chain of genesis records, capability attestations, delegation records, and audit anchors
- **Trust posture system**: Three verification modes -- disabled (default, backward compatible), permissive (log violations), and enforcing (block on violations)
- **Constraint dimensions**: Constraints that can only be tightened, never loosened, as they propagate through delegation chains
- **Knowledge ledger**: Provenance tracking for agent-generated knowledge
- **RFC 3161 timestamping**: Cryptographic time-stamping for audit trails

Trust context propagates through the Core SDK's `RuntimeTrustContext` (in `kailash.runtime.trust`), meaning trust verification works across all three frameworks when workflows execute in a trust-enabled context. Kaizen's `TrustedAgent` and `TrustedSupervisorAgent` extend BaseAgent with built-in trust establishment, capability verification, and trust delegation.

## LLM Provider Support

Kaizen supports 9 LLM providers with automatic detection:

| Provider      | Type    | Requirements                                                |
| ------------- | ------- | ----------------------------------------------------------- |
| `openai`      | Cloud   | `OPENAI_API_KEY`                                            |
| `azure`       | Cloud   | `AZURE_AI_INFERENCE_ENDPOINT`, `AZURE_AI_INFERENCE_API_KEY` |
| `anthropic`   | Cloud   | `ANTHROPIC_API_KEY`                                         |
| `google`      | Cloud   | `GOOGLE_API_KEY` or `GEMINI_API_KEY`                        |
| `ollama`      | Local   | Ollama running on port 11434                                |
| `docker`      | Local   | Docker Desktop Model Runner on port 12434                   |
| `cohere`      | Cloud   | `COHERE_API_KEY`                                            |
| `huggingface` | Local   | None (optional API key)                                     |
| `mock`        | Testing | None                                                        |

Auto-detection priority: OpenAI, Azure, Anthropic, Google, Ollama, Docker. Override with `KAIZEN_DEFAULT_PROVIDER` environment variable.

All model names should be read from environment variables, not hardcoded:

```python
import os
model = os.environ.get("OPENAI_PROD_MODEL", os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o"))
```

## Specialized Agents

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

### Vision Processing

```python
from kaizen.agents import VisionAgent, VisionAgentConfig

config = VisionAgentConfig(llm_provider="ollama", model="bakllava")
agent = VisionAgent(config=config)

result = agent.analyze(
    image="/path/to/receipt.jpg",      # File path, NOT base64
    question="What is the total?"      # Use 'question', NOT 'prompt'
)
print(result["answer"])                # Use 'answer', NOT 'response'
```

### Audio Transcription

```python
from kaizen.agents import TranscriptionAgent, TranscriptionAgentConfig

config = TranscriptionAgentConfig()  # Uses Whisper
agent = TranscriptionAgent(config=config)

result = agent.transcribe(audio_path="/path/to/audio.mp3")
print(result["transcription"])
```

## Multi-Agent Coordination

Kaizen implements the Google Agent-to-Agent (A2A) protocol for semantic capability matching. Agents are selected based on semantic similarity to the task, not hardcoded routing logic.

**OrchestrationRuntime** is the recommended approach for multi-agent coordination. `AgentTeam` is deprecated.

```python
from kaizen.orchestration.patterns import SupervisorWorkerPattern

pattern = SupervisorWorkerPattern(
    supervisor=supervisor_agent,
    workers=[qa_agent, code_agent, research_agent],
    coordinator=coordinator,
    shared_pool=shared_memory_pool
)

# Semantic task routing (no hardcoded if/else)
result = pattern.execute_task("Analyze this codebase and suggest improvements")
```

### Pipeline Patterns

9 composable pipeline patterns with factory methods:

```python
from kaizen.orchestration.pipeline import Pipeline

pipeline = Pipeline.sequential(agents=[agent1, agent2, agent3])
pipeline = Pipeline.supervisor_worker(supervisor, workers, selection_mode="semantic")
pipeline = Pipeline.router(agents=[...], routing_strategy="semantic")
pipeline = Pipeline.ensemble(agents=[...], synthesizer, discovery_mode="a2a", top_k=3)
pipeline = Pipeline.blackboard(specialists=[...], controller, max_iterations=5)
pipeline = Pipeline.consensus(agents=[...], threshold=0.67)
pipeline = Pipeline.debate(agents=[proponent, opponent], rounds=3, judge=judge)
pipeline = Pipeline.handoff(agents=[tier1, tier2, tier3])
pipeline = Pipeline.parallel(agents=[...], aggregator, max_workers=5)
```

## CARE/EATP Trust Framework

### Trust Lineage Chains

Cryptographically linked chains of genesis records, capability attestations, delegation records, and audit anchors:

```python
from kaizen.trust import TrustLineageChain, GenesisRecord

# Establish trust chain
chain = TrustLineageChain()
genesis = GenesisRecord(agent_id="agent-001", capabilities=["read", "write"])
chain.establish(genesis)
```

### Trusted Agents

BaseAgent extensions with built-in trust verification:

```python
from kaizen.trust import TrustedAgent, TrustedSupervisorAgent

# Agent with automatic trust establishment
agent = TrustedAgent(config=config, signature=signature)

# Supervisor that delegates with constraints
supervisor = TrustedSupervisorAgent(config=config)
```

### Trust-Aware Orchestration

```python
from kaizen.trust import TrustAwareOrchestrationRuntime, TrustPolicyEngine

runtime = TrustAwareOrchestrationRuntime(
    policy_engine=TrustPolicyEngine(),
)
```

### Secure Agent Communication

```python
from kaizen.trust import SecureChannel

channel = SecureChannel()
# HMAC-based message authentication
# Nonce-based replay protection
# Timestamp validation
```

## FallbackRouter Safety

The `FallbackRouter` includes safety mechanisms:

- `on_fallback` callback fires before each fallback attempt (raise `FallbackRejectedError` to block)
- WARNING-level logging on every fallback
- Model capability validation before routing

## MCP Integration

MCP session methods are wired and functional:

```python
# Discover MCP resources
resources = await agent.discover_mcp_resources()

# Read MCP resource
content = await agent.read_mcp_resource(uri="resource://example")

# Discover MCP prompts
prompts = await agent.discover_mcp_prompts()

# Get MCP prompt
prompt = await agent.get_mcp_prompt(name="my_prompt")
```

### 12 Builtin Tools (via MCP)

- **File (5)**: read_file, write_file, delete_file, list_directory, file_exists
- **HTTP (4)**: http_get, http_post, http_put, http_delete
- **Bash (1)**: bash_command
- **Web (2)**: fetch_url, extract_links

## Autonomous Tool Calling

```python
agent = BaseAgent(
    config=config,
    signature=signature,
    tools="all"  # Enable 12 builtin tools via MCP
)

# Discover and execute tools
tools = await agent.discover_tools(category="file", safe_only=True)
result = await agent.execute_tool(tool_name="read_file", params={"path": "data.txt"})

# Chain multiple tools
results = await agent.execute_tool_chain([
    {"tool_name": "read_file", "params": {"path": "input.txt"}},
    {"tool_name": "write_file", "params": {"path": "output.txt", "content": "..."}}
])
```

Tools are classified by danger level (SAFE, LOW, MEDIUM, HIGH). Non-SAFE tools require explicit approval via the Control Protocol.

## Control Protocol

Bidirectional agent-to-client communication:

```python
from kaizen.core.autonomy.control import ControlProtocol
from kaizen.core.autonomy.control.transports import CLITransport

protocol = ControlProtocol(CLITransport())

# Agent asks questions during execution
answer = await agent.ask_user_question("Which environment?", ["dev", "staging", "production"])

# Agent requests approval for dangerous operations
approved = await agent.request_approval("Delete old files?", {"files": ["old1.txt"]})

# Agent reports progress
await agent.report_progress("Processing files", percentage=50)
```

Transports: CLI, HTTP/SSE, stdio, memory.

## Lifecycle Infrastructure

### Hooks (Event-Driven Monitoring)

```python
from kaizen.core.autonomy.hooks.builtin import LoggingHook, MetricsHook, AuditHook

agent._hook_manager.register_hook(LoggingHook(log_level="INFO"))
agent._hook_manager.register_hook(MetricsHook())
agent._hook_manager.register_hook(AuditHook(audit_path="./audit"))
```

6 production-ready hooks: LoggingHook, MetricsHook, CostTrackingHook, PerformanceProfilerHook, AuditHook, TracingHook. Performance: <0.01ms overhead per event.

### State (Persistent Checkpoints)

```python
from kaizen.core.autonomy.state import StateManager, FilesystemStorage

storage = FilesystemStorage(base_path="./agent_state")
state_manager = StateManager(storage_backend=storage)

checkpoint_id = await state_manager.create_checkpoint(
    agent_id="my_agent",
    description="Before processing"
)
```

4 storage backends: Filesystem, Redis, PostgreSQL, S3.

### Interrupts (Graceful Shutdown)

```python
from kaizen.core.autonomy.interrupts import InterruptSignal

agent._interrupt_manager.request_interrupt(
    signal=InterruptSignal.USER_REQUESTED,
    reason="Awaiting approval"
)
```

3 interrupt sources (USER, SYSTEM, PROGRAMMATIC), 2 shutdown modes (GRACEFUL, IMMEDIATE).

## Memory System

### Persistent Buffer Memory

```python
from kaizen.memory import PersistentBufferMemory
from dataflow import DataFlow

db = DataFlow(database_type="sqlite", database_config={"database": "./memory.db"})

memory = PersistentBufferMemory(
    db=db,
    agent_id="agent_001",
    buffer_size=100,
    auto_persist_interval=10,
    enable_compression=True
)
```

### Memory Types

- **ShortTermMemory**: Session-scoped, in-memory, fast retrieval (<10ms)
- **LongTermMemory**: Persistent with SQLite/PostgreSQL backends, semantic search
- **SemanticMemory**: Vector-based similarity search with embeddings

### Learning Mechanisms

- **PatternRecognition**: Detect FAQs and common workflows
- **PreferenceLearning**: Learn user preferences from interactions
- **ErrorCorrection**: Record errors and corrections to avoid repeats

## Permission System

```python
from kaizen.core.autonomy.permissions import ExecutionContext, PermissionMode

context = ExecutionContext(
    mode=PermissionMode.DEFAULT,
    budget_limit=50.0,
    allowed_tools={"read_file", "http_get"},
    denied_tools={"delete_file"}
)
```

4 permission modes: DEFAULT, ACCEPT_EDITS, PLAN, BYPASS. 3 permission types: ALLOW, DENY, ASK.

## Observability

Production-ready observability with -0.06% overhead:

```python
agent.enable_observability(
    service_name="my-agent",
    enable_metrics=True,      # Prometheus
    enable_logging=True,      # Structured JSON for ELK
    enable_tracing=True,      # OpenTelemetry + Jaeger
    enable_audit=True,        # Immutable JSONL (SOC2/GDPR/HIPAA)
)
```

## Document Extraction and RAG

```python
from kaizen.agents.multi_modal import DocumentExtractionAgent, DocumentExtractionConfig

config = DocumentExtractionConfig(
    provider="ollama_vision",  # $0.00 cost
    chunk_for_rag=True,
    chunk_size=512,
    overlap=50,
)

agent = DocumentExtractionAgent(config=config)
result = agent.extract(file_path="report.pdf", chunk_for_rag=True)

for chunk in result["chunks"]:
    print(f"Page {chunk['page']}: {chunk['text'][:100]}...")
```

3 providers: Ollama (free), OpenAI Vision (~$0.01/page), Landing AI (~$0.05/page, 95%+ accuracy).

## Integration with DataFlow

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

db = DataFlow()

@db.model
class QASession:
    question: str
    answer: str
    confidence: float

agent = QAAgent(QAConfig())
result = agent.ask("What is the capital of France?")

workflow = WorkflowBuilder()
workflow.add_node("QASessionCreateNode", "store", {
    "question": "What is the capital of France?",
    "answer": result["answer"],
    "confidence": result["confidence"]
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Integration with Nexus

```python
from nexus import Nexus

nexus = Nexus()

agent = QAAgent(QAConfig())
agent_workflow = agent.to_workflow()
nexus.register("qa_agent", agent_workflow.build())

# Available on all channels:
# API:  POST /workflows/qa_agent
# CLI:  nexus run qa_agent --question "What is AI?"
# MCP:  qa_agent tool for AI assistants
nexus.start()
```

## Testing

3-tier testing strategy with no mocking in Tiers 2-3:

```bash
# Tier 1: Unit tests (fast, mocked LLM)
pytest tests/unit/

# Tier 2: Integration tests (real Ollama, free)
pytest tests/integration/

# Tier 3: E2E tests (real OpenAI, budget-controlled)
pytest tests/e2e/
```

## Environment Configuration

```bash
# Required API Keys (.env)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Model names (read from .env, never hardcode)
DEFAULT_LLM_MODEL=gpt-4o
OPENAI_PROD_MODEL=gpt-4o

# Optional
KAIZEN_LOG_LEVEL=INFO
KAIZEN_DEFAULT_PROVIDER=openai
```

## Common Mistakes

1. **Not loading .env**: Always call `load_dotenv()` before using agents
2. **Hardcoding model names**: Read from `os.environ`, never use string literals like `"gpt-4"`
3. **Wrong Vision API**: Use `question` parameter and `answer` key, not `prompt`/`response`
4. **Using BaseAgentConfig directly**: Use domain configs (e.g., `QAConfig`), BaseAgent auto-converts
5. **Using AgentTeam**: Deprecated. Use `OrchestrationRuntime` instead

## Documentation

- [Kaizen CLAUDE.md](CLAUDE.md) -- Quick reference for Claude Code (1,900+ lines)
- [Installation Guide](docs/getting-started/installation.md)
- [Quickstart Tutorial](docs/getting-started/quickstart.md)
- [Signature Programming](docs/guides/signature-programming.md)
- [BaseAgent Architecture](docs/guides/baseagent-architecture.md)
- [Multi-Modal Processing](docs/guides/multi-modal.md)
- [Multi-Agent Coordination](docs/guides/multi-agent.md)
- [Hooks System](docs/guides/hooks-system.md)
- [Control Protocol](docs/guides/control-protocol-tutorial.md)
- [API Reference](docs/reference/api-reference.md)
- [Troubleshooting](docs/reference/troubleshooting.md)

## Version History

- **v1.2.1**: Current stable release. CARE/EATP trust framework, FallbackRouter safety, MCP session methods
- **v1.0.0**: GA release. Performance optimization (10-100x), specialist system, GPT-5 support
- **v0.9.0**: Journey Orchestration (declarative pathways, intent detection)
- **v0.8.0**: Enterprise Agent Trust Protocol (EATP), secure communication, trust-aware orchestration
- **v0.6.0**: Interrupt mechanism, persistent buffer memory, enhanced hooks
