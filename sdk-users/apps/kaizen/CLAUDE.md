# Kaizen - Quick Reference for Claude Code

## 🚀 What is Kaizen?

**Kaizen** is a signature-based AI agent framework built on Kailash Core SDK, providing production-ready agents with multi-modal processing, multi-agent coordination, and enterprise features.

## 🆕 What's New in v0.9.0 (2026-01)

**Journey Orchestration (Layer 5)** - Declarative user journey management with intent-driven transitions:

```python
from kaizen.journey import Journey, Pathway, Transition, IntentTrigger, JourneyConfig

# Define signatures with Layer 2 enhancements
class IntakeSignature(Signature):
    __intent__ = "Gather patient symptoms and preferences"
    __guidelines__ = ["Ask symptoms before demographics", "Use empathetic language"]

    message: str = InputField(desc="Patient message")
    symptoms: list = OutputField(desc="Extracted symptoms")

# Define Journey with nested Pathways
class PatientJourney(Journey):
    __entry_pathway__ = "intake"
    __transitions__ = [
        Transition(
            trigger=IntentTrigger(intents=["help", "faq"]),
            to_pathway="faq"
        )
    ]

    class IntakePath(Pathway):
        __signature__ = IntakeSignature
        __agents__ = ["intake_agent"]
        __accumulate__ = ["symptoms", "preferences"]
        __next__ = "booking"

    class FAQPath(Pathway):
        __return_behavior__ = ReturnToPrevious()  # Returns to previous pathway

# Run the Journey
journey = PatientJourney(session_id="patient-123", config=JourneyConfig())
journey.manager.register_agent("intake_agent", intake_agent)
await journey.start()
response = await journey.process_message("I have back pain")
```

**Key Features:**
- **Declarative Pathways**: Define multi-step user flows as nested classes
- **Intent Detection**: LLM-powered intent classification (not keyword/regex)
- **Context Accumulation**: Persist data across pathways with merge strategies (REPLACE, APPEND, UNION, SUM)
- **Return Behaviors**: ReturnToPrevious for detours (FAQ, help), ReturnToSpecific for error handling
- **Nexus Deployment**: Deploy journeys via API/CLI/MCP with `deploy_journey_to_nexus()`
- **Hooks System**: 9 lifecycle events (PRE/POST_PATHWAY_EXECUTE, PRE/POST_TRANSITION, etc.)

**Reference Implementation**: `examples/journey/healthcare_referral/` (5 pathways, 3 transitions)

**Production Validated**: 301 unit + 50 integration tests (351 total)

---

## What Was New in v0.8.0 (2026-01)

**Enterprise Agent Trust Protocol (EATP)**:

- **🔐 Trust Lineage Chains**
  - Cryptographically linked chain of genesis, capabilities, delegations, and audit anchors
  - TrustLineageChain with GenesisRecord, CapabilityAttestation, DelegationRecord, AuditAnchor
  - 4 core operations: ESTABLISH, DELEGATE, VERIFY, AUDIT
  - PostgresTrustStore for persistent storage with caching

- **🤖 TrustedAgent & TrustedSupervisorAgent**
  - BaseAgent extensions with built-in trust verification
  - Automatic trust establishment and capability verification
  - Trust delegation with constraints and time limits
  - Trust context propagation through workflows

- **📡 Secure Agent Communication**
  - SecureChannel with HMAC-based message authentication
  - Nonce-based replay protection (InMemoryReplayProtection)
  - Timestamp validation and sender/receiver verification
  - MessageSigner and MessageVerifier for end-to-end security

- **🏗️ Trust-Aware Orchestration**
  - TrustAwareOrchestrationRuntime with trust context propagation
  - TrustPolicyEngine for policy-based trust evaluation
  - TrustExecutionContext for capability and delegation tracking
  - Integration with existing orchestration patterns

- **🏢 Enterprise System Agent (ESA)**
  - Proxy agents for legacy systems with trust verification
  - SystemMetadata and SystemConnectionInfo for system configuration
  - Bridge non-AI systems into trust ecosystem
  - Accountability for external system calls

- **🌐 A2A HTTP Service**
  - REST/JSON-RPC API for trust operations
  - AgentCardGenerator for agent capability cards
  - Cross-organization agent coordination
  - Integration with existing A2A protocol

- **🛡️ Security Hardening**
  - CredentialRotationManager for automatic key rotation
  - TrustRateLimiter for rate limiting trust operations
  - SecurityAuditLogger for security event logging
  - SecureKeyStorage for encrypted key storage

**Version**: 0.8.0 | **Dependencies**: Kailash >=0.10.13

---

## What Was New in v0.6.0

**Enhanced Autonomy & Memory Systems**:

- **🎯 Interrupt Mechanism (Production-Ready)**
  - Complete graceful shutdown with Ctrl+C handling
  - 3 interrupt sources: USER (Ctrl+C), SYSTEM (timeout/budget), PROGRAMMATIC (API/hooks)
  - 2 shutdown modes: GRACEFUL (finish cycle + checkpoint) vs IMMEDIATE (stop now)
  - Signal propagation across multi-agent hierarchies
  - 34 E2E tests production-validated
  - Examples: `examples/autonomy/interrupts/` (ctrl_c, timeout, budget)

- **💾 Persistent Buffer Memory (DataFlow Backend)**
  - Dual-buffer architecture: In-memory + database storage
  - Auto-persist with configurable intervals
  - JSONL compression (60%+ storage reduction)
  - Cross-session conversation persistence
  - Multi-instance agent isolation
  - 28 E2E tests with real database operations

- **🔄 Enhanced Hooks System**
  - New hook events: PRE/POST_INTERRUPT, PRE/POST_CHECKPOINT_SAVE
  - Improved performance: <0.01ms overhead (625x better than target)
  - Production-validated: 100+ concurrent hooks supported

---

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

### LLM Provider Configuration (v0.8.2)

Kaizen supports 9 LLM providers with automatic detection:

| Provider | Type | Requirements | Features |
|----------|------|--------------|----------|
| `openai` | Cloud | `OPENAI_API_KEY` | GPT-4, GPT-4o, structured outputs, tool calling |
| `azure` | Cloud | `AZURE_AI_INFERENCE_ENDPOINT`, `AZURE_AI_INFERENCE_API_KEY` | Azure AI Foundry, vision, embeddings, structured outputs |
| `anthropic` | Cloud | `ANTHROPIC_API_KEY` | Claude 3.x, vision support |
| `google` | Cloud | `GOOGLE_API_KEY` or `GEMINI_API_KEY` | Gemini 2.0, vision, embeddings, tool calling, structured outputs |
| `ollama` | Local | Ollama running on port 11434 | Free, local models |
| `docker` | Local | Docker Desktop Model Runner on port 12434 | Free local inference, GPU acceleration |
| `cohere` | Cloud | `COHERE_API_KEY` | Command models, embeddings |
| `huggingface` | Local | None | Sentence transformers, embeddings |
| `mock` | Testing | None | Unit test provider |

```python
# Azure AI Foundry (v0.7.1)
@dataclass
class AzureConfig:
    llm_provider: str = "azure"
    model: str = "gpt-4o"
    # Set: AZURE_AI_INFERENCE_ENDPOINT, AZURE_AI_INFERENCE_API_KEY

# Docker Model Runner (FREE local, v0.7.1)
@dataclass
class DockerConfig:
    llm_provider: str = "docker"
    model: str = "ai/llama3.2"  # Or ai/qwen3, ai/gemma3
    # Prerequisites: docker desktop enable model-runner --tcp 12434

# Google Gemini (Cloud, multimodal, v0.8.2)
@dataclass
class GoogleConfig:
    llm_provider: str = "google"  # Or "gemini" (alias)
    model: str = "gemini-2.0-flash"  # Or gemini-1.5-pro
    # Set: GOOGLE_API_KEY or GEMINI_API_KEY
    # Install: pip install kailash-kaizen[google]
```

**Auto-Detection Order**: OpenAI → Azure → Anthropic → Google → Ollama → Docker

**Docker Tool Calling**: Model-dependent. Supported: `ai/qwen3`, `ai/llama3.3`, `ai/gemma3`

**Google Gemini**: Chat, vision (multimodal), embeddings (text-embedding-004), tool calling, async support

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
from kaizen.orchestration.patterns import SupervisorWorkerPattern

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

### Multi-Provider Structured Outputs (v0.8.2)

**Guarantee LLM responses match your signature** with 100% schema compliance across OpenAI, Google/Gemini, and Azure.

#### Automatic Configuration (Recommended)

**Most users don't need any configuration!** Structured outputs are **automatically enabled** when you use BaseAgent with a signature:

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from kaizen.core.config import BaseAgentConfig

class AnalysisSignature(Signature):
    input_text: str = InputField(desc="Text to analyze")
    category: str = OutputField(desc="Classification category")
    confidence: float = OutputField(desc="Confidence 0-1")

# Structured outputs auto-configured - NO provider_config needed!
config = BaseAgentConfig(
    llm_provider="openai",  # or "google", "gemini", "azure"
    model="gpt-4o-2024-08-06"
)

agent = BaseAgent(config=config, signature=AnalysisSignature())
result = agent.run(input_text="Sample text")

# Response guaranteed to have all fields with correct types
print(result['category'])      # Always present, always string
print(result['confidence'])    # Always present, always float
```

**How Auto-Configuration Works**: When a signature is provided and no `provider_config` is set, WorkflowGenerator automatically calls `create_structured_output_config()` with strict mode enabled.

#### Manual Configuration (Advanced)

For explicit control over structured output behavior:

```python
from kaizen.core.structured_output import create_structured_output_config

# Only needed when you want to override defaults
config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4o-2024-08-06",
    provider_config=create_structured_output_config(
        signature=AnalysisSignature(),
        strict=True,  # 100% schema compliance (default)
        name="analysis"  # Custom schema name
    )
)
```

**How It Works:**
- All providers receive OpenAI-style `response_format` from `create_structured_output_config()`
- Each provider auto-translates to native parameters:
  - **OpenAI**: Uses `response_format` directly
  - **Google/Gemini**: Translates to `response_mime_type` + `response_schema`
  - **Azure**: Translates to `JsonSchemaFormat`
- Dict responses are returned directly without string parsing - transparent to users

**Provider Support Matrix:**
- ✅ **OpenAI**: Full support (`json_schema` strict, `json_object` legacy)
- ✅ **Google/Gemini**: Full support (auto-translated)
- ✅ **Azure AI Foundry**: Full support (auto-translated)
- ❌ **Ollama/Anthropic**: Not supported

**Modes:**
- **Strict Mode** (`strict=True`): 100% compliance
- **Legacy Mode** (`strict=False`): ~70-85% compliance

**Learn More:** [Structured Outputs Guide](docs/guides/signature-programming.md)

### Pipeline Patterns

**9 composable pipeline patterns** with factory methods on `Pipeline` class:

```python
from kaizen.orchestration.pipeline import Pipeline

# 1. Sequential - Linear step-by-step processing
pipeline = Pipeline.sequential(agents=[agent1, agent2, agent3])

# 2. Supervisor-Worker - Task decomposition with A2A semantic worker selection
pipeline = Pipeline.supervisor_worker(supervisor, workers, selection_mode="semantic")

# 3. Router - Intelligent routing via A2A capability matching
pipeline = Pipeline.router(agents=[...], routing_strategy="semantic")

# 4. Ensemble - Multi-perspective with A2A agent discovery (top-k)
pipeline = Pipeline.ensemble(agents=[...], synthesizer, discovery_mode="a2a", top_k=3)

# 5. Blackboard - Iterative specialist collaboration with A2A selection
pipeline = Pipeline.blackboard(specialists=[...], controller, selection_mode="semantic", max_iterations=5)

# 6. Consensus - Democratic voting for agreement
pipeline = Pipeline.consensus(agents=[...], threshold=0.67, voting_strategy="majority")

# 7. Debate - Adversarial analysis with proponent/opponent
pipeline = Pipeline.debate(agents=[proponent, opponent], rounds=3, judge)

# 8. Handoff - Tier escalation based on complexity
pipeline = Pipeline.handoff(agents=[tier1, tier2, tier3])

# 9. Parallel - Concurrent execution for 10-100x speedup
pipeline = Pipeline.parallel(agents=[...], aggregator, max_workers=5, timeout=30)

# All pipelines can be converted to BaseAgent
agent = pipeline.to_agent(name="my_pipeline")
```

**A2A Integration** (4 patterns):
- ✅ **Router**: Semantic routing to best agent
- ✅ **Supervisor-Worker**: Semantic worker selection
- ✅ **Ensemble**: Agent discovery (top-k)
- ✅ **Blackboard**: Dynamic specialist selection

### Single-Agent Patterns

**3 advanced patterns for structured workflows, iterative refinement, and multi-path exploration:**

```python
# 1. Planning Agent - Plan Before You Act
from kaizen.agents.specialized.planning import PlanningAgent, PlanningConfig

agent = PlanningAgent(PlanningConfig(
    max_plan_steps=5,
    validation_mode="strict",  # Pre-execution validation
    enable_replanning=True
))
result = agent.run(task="Create research report", context={"length": "2000 words"})
# Three-phase: Plan → Validate → Execute

# 2. PEV Agent - Plan, Execute, Verify, Refine
from kaizen.agents.specialized.pev import PEVAgent, PEVAgentConfig

agent = PEVAgent(PEVAgentConfig(
    max_iterations=5,  # Iterative refinement cycles
    verification_strictness="medium",  # Post-execution verification
    enable_error_recovery=True
))
result = agent.run(task="Generate production-ready code")
# Iterative: Plan → Execute → Verify → Refine (loop until verified)

# 3. Tree-of-Thoughts Agent - Multi-Path Exploration
from kaizen.agents.specialized.tree_of_thoughts import ToTAgent, ToTAgentConfig

agent = ToTAgent(ToTAgentConfig(
    num_paths=5,  # Generate 5 alternative paths
    temperature=0.9,  # HIGH for diversity
    evaluation_criteria="quality",
    parallel_execution=True
))
result = agent.run(task="Strategic decision: choose go-to-market strategy")
# Parallel: Generate N paths → Evaluate → Select Best → Execute
```

**Pattern Selection Guide**:
- **Planning**: Structured workflows with validation BEFORE execution (research, compliance)
- **PEV**: Iterative refinement with verification AFTER execution (code generation, quality-critical)
- **Tree-of-Thoughts**: Explore multiple alternatives, select best (strategic decisions, creative tasks)

**Comparison Table**:

| Pattern | Planning Phase | Verification | Cycles | Best For |
|---------|---------------|--------------|--------|----------|
| **Planning** | ✅ Upfront | Pre-execution | 1 (or replan) | Structured workflows |
| **PEV** | ✅ Initial | Post-execution | Multiple refine | Quality-critical |
| **ToT** | ❌ | Score evaluation | 1 generation | Alternatives exploration |
| **ReAct** | ❌ | Observation | Variable | Real-time adaptation |
| **CoT** | ❌ | ❌ | 1 | Step-by-step reasoning |

**See Comprehensive Guides**:
- [Planning Agent Guide](docs/guides/planning-agent.md) - 200+ lines
- [PEV Agent Guide](docs/guides/pev-agent.md) - 200+ lines
- [Tree-of-Thoughts Guide](docs/guides/tree-of-thoughts-agent.md) - 200+ lines
- [Single-Agent Patterns Overview](docs/guides/single-agent-patterns.md) - All patterns comparison

## 🎯 Core API

### Available Specialized Agents

**Implemented and Production-Ready:**
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

### Tool Calling

**MCP (Model Context Protocol) integration - Auto-connects to 12 builtin tools:**

```python
from kaizen.core.base_agent import BaseAgent

# MCP auto-connect - 12 builtin tools available automatically
agent = BaseAgent(
    config=config,
    signature=signature
    # Optional: Add custom MCP servers
    # mcp_servers=[{
    #     "name": "custom-server",
    #     "command": "python",
    #     "args": ["-m", "custom.mcp.server"],
    #     "transport": "stdio"
    # }]
)

# Discover tools (from kaizen_builtin MCP server)
tools = await agent.discover_mcp_tools(server_name="kaizen_builtin")

# Execute single tool
result = await agent.execute_mcp_tool(
    tool_name="mcp__kaizen_builtin__read_file",
    params={"path": "data.txt"}
)
```

**12 Builtin Tools** (via kaizen_builtin MCP server):
- **File (5)**: read_file, write_file, delete_file, list_directory, file_exists
- **HTTP (4)**: http_get, http_post, http_put, http_delete
- **Bash (1)**: bash_command
- **Web (2)**: fetch_url, extract_links

**Universal Support**: All agents inherit MCP integration from BaseAgent (100% backward compatible)

### Control Protocol

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

### Observability & Performance Monitoring

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

**Production Validated:**
- -0.06% overhead (essentially zero, tested with 100 real OpenAI API calls)
- 0.57ms p95 audit latency (<10ms target, 17.5x margin)
- 281 tests passing - Validated with real infrastructure (NO MOCKING in Tiers 2-3 tests)

**Start Observability Stack:**
```bash
cd docs/observability
docker-compose up -d  # Starts Jaeger, Prometheus, Grafana, ELK Stack
```

### Lifecycle Infrastructure

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

# 3. Interrupts - Graceful shutdown for autonomous agents
from kaizen.agents.autonomous.base import BaseAutonomousAgent
from kaizen.agents.autonomous.config import AutonomousConfig
from kaizen.core.autonomy.interrupts.handlers import TimeoutInterruptHandler, BudgetInterruptHandler

# Enable interrupts in config
config = AutonomousConfig(
    llm_provider="ollama",
    model="llama3.2:1b",
    enable_interrupts=True,              # Enable interrupt handling
    graceful_shutdown_timeout=5.0,       # Max time for graceful shutdown
    checkpoint_on_interrupt=True         # Save checkpoint before exit
)

# Create autonomous agent
autonomous_agent = BaseAutonomousAgent(config=config, signature=MySignature())

# Add interrupt handlers
timeout_handler = TimeoutInterruptHandler(timeout_seconds=30.0)
autonomous_agent.interrupt_manager.add_handler(timeout_handler)

budget_handler = BudgetInterruptHandler(budget_limit=5.0)
autonomous_agent.interrupt_manager.add_handler(budget_handler)

# Run agent - gracefully handles Ctrl+C, timeouts, budget limits
try:
    result = await autonomous_agent.run_autonomous(task="Analyze data")
except InterruptedError as e:
    print(f"Agent interrupted: {e.reason.message}")
    checkpoint_id = e.reason.metadata.get("checkpoint_id")
```

**Key Components:**
- **6 Builtin Hooks**: LoggingHook, MetricsHook, CostTrackingHook, PerformanceProfilerHook, AuditHook, TracingHook
- **4 Storage Backends**: Filesystem, Redis, PostgreSQL, S3
- **Interrupt System**: Graceful shutdown for Ctrl+C, timeouts, budget limits with automatic checkpointing
  - **3 Interrupt Sources**: USER (Ctrl+C/SIGTERM), SYSTEM (timeout, budget, resources), PROGRAMMATIC (API, hooks)
  - **2 Shutdown Modes**: GRACEFUL (finish cycle, save checkpoint) vs IMMEDIATE (stop now, best-effort)
  - **3 Builtin Handlers**: TimeoutInterruptHandler, BudgetInterruptHandler, ResourceInterruptHandler
  - **Examples**: `examples/autonomy/interrupts/` (ctrl_c, timeout, budget)

### Persistent Buffer Memory (v0.6.0)

**DataFlow-backed conversation persistence with dual-buffer architecture:**

```python
from kaizen.memory import PersistentBufferMemory
from dataflow import DataFlow

# Initialize DataFlow backend (automatic schema creation)
db = DataFlow(
    database_type="sqlite",
    database_config={"database": "./agent_memory.db"}
)

# Create persistent buffer memory
memory = PersistentBufferMemory(
    db=db,
    agent_id="agent_001",
    buffer_size=100,              # Keep last 100 messages in memory
    auto_persist_interval=10,     # Auto-persist every 10 messages
    enable_compression=True       # JSONL compression for storage
)

# Add conversation turns
memory.add_message(role="user", content="What is AI?")
memory.add_message(role="assistant", content="AI is artificial intelligence...")

# Retrieve conversation history
history = memory.get_history(limit=10)  # Last 10 messages

# Persist to database
memory.persist()  # Manual persist (or waits for auto_persist_interval)

# Load from database in next session
memory_loaded = PersistentBufferMemory(db=db, agent_id="agent_001")
memory_loaded.load_from_db()  # Restores conversation history
```

**Conversational Agent Pattern:**
```python
from kaizen.agents import SimpleQAAgent
from kaizen.memory import PersistentBufferMemory

class ConversationalAgent(SimpleQAAgent):
    def __init__(self, config, db):
        super().__init__(config)
        self.memory = PersistentBufferMemory(
            db=db,
            agent_id=self.agent_id,
            buffer_size=50,
            auto_persist_interval=5
        )
        # Load previous conversations
        self.memory.load_from_db()

    def ask(self, question: str) -> dict:
        # Add user message to memory
        self.memory.add_message(role="user", content=question)

        # Get conversation context
        history = self.memory.get_history(limit=10)

        # Run agent with context
        result = self.run(question=question, context=history)

        # Add assistant response to memory
        self.memory.add_message(role="assistant", content=result["answer"])

        return result

# Usage - conversation persists across sessions
agent = ConversationalAgent(config, db)
result1 = agent.ask("What is AI?")
result2 = agent.ask("Can you elaborate?")  # Uses history from previous question

# Restart - history preserved
agent2 = ConversationalAgent(config, db)
result3 = agent2.ask("What did we discuss?")  # Remembers previous conversation
```

**Key Features:**
- **Dual-Buffer**: In-memory buffer (<1ms retrieval) + database storage
- **Auto-Persist**: Configurable auto-persist interval (every N messages)
- **Compression**: JSONL compression reduces storage by 60%+
- **Multi-Instance**: Agent-specific memory isolation with agent_id scoping
- **Cross-Session**: Load conversation history across restarts
- **Database Support**: SQLite (default), PostgreSQL
- **Production-Validated**: 28 E2E tests with real database operations

### Permission System

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

### Memory & Learning System

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

**Performance (Production validated):**
- <50ms retrieval (p95)
- <100ms storage (p95)
- 10,000+ entries per agent (SQLite)
- Millions of entries (PostgreSQL)
- 281 tests passing
**Use Cases:**
- Conversational agents with context continuity
- Customer support bots with preference learning
- Research agents that learn from feedback
- Code generation agents that avoid past errors
- Multi-agent systems with shared knowledge

### Document Extraction & RAG

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

**Production Validated:**
- 281 tests passing - Real infrastructure testing (NO MOCKING)
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
    question: str = InputField(desc="User input")  # 'description=' also works
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
- **[Hooks System](docs/guides/hooks-system.md)** - Event-driven monitoring and lifecycle hooks
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
- **[Performance Benchmarks](../../../apps/kailash-kaizen/docs/benchmarks/BENCHMARK_GUIDE.md)** - Measure performance across 7 key areas with statistical rigor (p50/p95/p99 percentiles)
- **[Troubleshooting](docs/reference/troubleshooting.md)** - Common issues

### Examples
- **[Autonomy Example Gallery](../../../apps/kailash-kaizen/examples/autonomy/EXAMPLE_GALLERY.md)** - 15 production-ready autonomy examples with learning paths (Tool Calling, Planning, Meta-Controller, Memory, Checkpoints, Interrupts, Full Integration)
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
from kaizen.orchestration.patterns import SupervisorWorkerPattern
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

## 🤖 Autonomy Infrastructure (6 Subsystems)

Kaizen provides production-ready autonomy infrastructure for building self-managing, observable, and resilient agents.

### 1. Hooks System - Event-Driven Observability

Zero-code-change monitoring via lifecycle events with production security.

**Quick Start:**
```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.autonomy.hooks.builtin import LoggingHook, MetricsHook, AuditHook

# Create agent
agent = BaseAgent(config=config, signature=signature)

# Register hooks for lifecycle events
agent._hook_manager.register_hook(LoggingHook(log_level="INFO"))
agent._hook_manager.register_hook(MetricsHook(export_interval=60))
agent._hook_manager.register_hook(AuditHook(storage_path="./audit_logs"))

# All agent operations now tracked automatically (zero overhead)
result = agent.run(question="What is AI?")
```

**Lifecycle Events:**
- PRE/POST_AGENT_LOOP: Agent execution start/end
- PRE/POST_TOOL_USE: Tool invocation monitoring
- PRE/POST_CHECKPOINT_SAVE: State persistence events
- PRE/POST_INTERRUPT: Graceful shutdown events

**Production Security:**
- RBAC authorization with role-based access control
- Ed25519 signature verification for hook authenticity
- Process isolation with resource limits (CPU/memory/timeout)
- API key authentication for metrics endpoints
- Sensitive data redaction (PII, credentials)
- Rate limiting and input validation

**Performance:**
- <0.01ms overhead per event (625x better than 10ms target)
- 100+ concurrent hooks supported
- Thread-safe and composable
- 281 tests passing
**See:** `docs/guides/hooks-system-guide.md` for complete documentation.

### 2. Checkpoint System - Persistent State Management

Save/load/fork agent state for failure recovery, debugging, and experimentation.

**Quick Start:**
```python
from kaizen.core.autonomy.state import StateManager, FilesystemStorage
from kaizen.core.autonomy.checkpoints import CheckpointManager

# Initialize storage backend
storage = FilesystemStorage(base_path="./agent_state")
state_manager = StateManager(storage_backend=storage)

# Create checkpoint before risky operation
checkpoint_id = await state_manager.create_checkpoint(
    agent_id=agent.agent_id,
    description="Before data processing",
    state_data={"conversation": history, "context": context}
)

# Execute agent
try:
    result = agent.run(question="Process data")
    await state_manager.save_state(current_state)
except Exception as e:
    # Restore from checkpoint on failure
    restored_state = await state_manager.load_checkpoint(checkpoint_id)
    agent.restore_state(restored_state)
```

**Storage Backends:**
- **FilesystemStorage**: Local file-based, compressed checkpoints
- **RedisStorage**: Fast in-memory checkpoints with TTL
- **PostgreSQLStorage**: Enterprise-scale with versioning
- **S3Storage**: Distributed, highly available storage

**Features:**
- Automatic compression (50-70% reduction)
- Incremental checkpoints (only changed state)
- State versioning and deduplication
- Fork checkpoints for experimentation
- Automatic cleanup of old checkpoints

**Use Cases:**
- Failure recovery for long-running agents
- Debugging by forking from specific states
- A/B testing with different strategies
- Time-travel debugging

**See:** `docs/guides/state-persistence-guide.md` for complete documentation.

### 3. Interrupt Mechanism - Graceful Shutdown

Graceful execution control for autonomous agents with Ctrl+C handling, timeouts, and budget limits.

**Quick Start:**
```python
from kaizen.agents.autonomous.base import BaseAutonomousAgent
from kaizen.agents.autonomous.config import AutonomousConfig
from kaizen.core.autonomy.interrupts.handlers import TimeoutInterruptHandler, BudgetInterruptHandler

# Enable interrupts in config
config = AutonomousConfig(
    llm_provider="ollama",
    model="llama3.2:1b",
    enable_interrupts=True,              # Enable interrupt handling
    graceful_shutdown_timeout=5.0,       # Max time for graceful shutdown
    checkpoint_on_interrupt=True         # Save checkpoint before exit
)

# Create autonomous agent
agent = BaseAutonomousAgent(config=config, signature=MySignature())

# Add interrupt handlers
timeout_handler = TimeoutInterruptHandler(timeout_seconds=30.0)
agent.interrupt_manager.add_handler(timeout_handler)

budget_handler = BudgetInterruptHandler(budget_limit=5.0)  # $5 limit
agent.interrupt_manager.add_handler(budget_handler)

# Run agent - gracefully handles Ctrl+C, timeouts, budget limits
try:
    result = await agent.run_autonomous(task="Analyze data")
except InterruptedError as e:
    print(f"Agent interrupted: {e.reason.message}")
    checkpoint_id = e.reason.metadata.get("checkpoint_id")
```

**Interrupt Sources:**
- **USER**: Ctrl+C (SIGTERM/SIGINT), user-initiated stop
- **SYSTEM**: Timeout, budget limit, resource exhaustion
- **PROGRAMMATIC**: API calls, hook-triggered stops

**Shutdown Modes:**
- **GRACEFUL**: Finish current cycle, save checkpoint, clean shutdown (default)
- **IMMEDIATE**: Stop now, best-effort checkpoint, fast exit

**Features:**
- Signal propagation across multi-agent hierarchies
- Automatic checkpoint preservation
- Graceful timeout with configurable shutdown window
- Budget tracking and auto-stop
- 34 E2E tests production-validated

**Examples:** `examples/autonomy/interrupts/` (ctrl_c, timeout, budget)

**See:** `docs/guides/interrupt-mechanism-guide.md` for complete documentation.

### 4. Memory System - 3-Tier Hierarchical Storage

Production-ready memory system with hot/warm/cold tiers for conversational agents.

**Quick Start:**
```python
from kaizen.memory import PersistentBufferMemory
from dataflow import DataFlow

# Initialize DataFlow backend (automatic schema creation)
db = DataFlow(
    database_type="sqlite",
    database_config={"database": "./agent_memory.db"}
)

# Create persistent buffer memory (Hot + Warm tiers)
memory = PersistentBufferMemory(
    db=db,
    agent_id="agent_001",
    buffer_size=100,              # Hot tier: last 100 messages in memory
    auto_persist_interval=10,     # Warm tier: auto-persist every 10 messages
    enable_compression=True       # JSONL compression for storage (60%+ reduction)
)

# Add conversation turns
memory.add_message(role="user", content="What is AI?")
memory.add_message(role="assistant", content="AI is artificial intelligence...")

# Retrieve conversation history (Hot tier: <1ms)
history = memory.get_history(limit=10)  # Last 10 messages

# Persist to database (Warm tier: 10-50ms)
memory.persist()  # Manual persist (or waits for auto_persist_interval)

# Load from database in next session
memory_loaded = PersistentBufferMemory(db=db, agent_id="agent_001")
memory_loaded.load_from_db()  # Restores conversation history
```

**3-Tier Architecture:**

| Tier | Storage | Latency | Capacity | Use Case |
|------|---------|---------|----------|----------|
| **Hot** | In-memory buffer | <1ms | Last 100 messages | Active conversation |
| **Warm** | Database (SQLite/PostgreSQL) | 10-50ms | Agent-specific history | Session continuity |
| **Cold** | Object storage (S3/MinIO) | 100ms+ | Long-term archival | Multi-hour conversations |

**Features:**
- **Dual-Buffer Architecture**: In-memory + database for optimal performance
- **Auto-Persist**: Configurable intervals (every N messages)
- **JSONL Compression**: 60%+ storage reduction for warm/cold tiers
- **Multi-Instance Isolation**: Agent-specific memory with agent_id scoping
- **Cross-Session Persistence**: Load conversation history across restarts
- **DataFlow Integration**: Automatic schema creation and migration

**Conversational Agent Pattern:**
```python
from kaizen.agents import SimpleQAAgent
from kaizen.memory import PersistentBufferMemory

class ConversationalAgent(SimpleQAAgent):
    def __init__(self, config, db):
        super().__init__(config)
        self.memory = PersistentBufferMemory(
            db=db,
            agent_id=self.agent_id,
            buffer_size=50,
            auto_persist_interval=5
        )
        # Load previous conversations
        self.memory.load_from_db()

    def ask(self, question: str) -> dict:
        # Add user message to memory
        self.memory.add_message(role="user", content=question)

        # Get conversation context
        history = self.memory.get_history(limit=10)

        # Run agent with context
        result = self.run(question=question, context=history)

        # Add assistant response to memory
        self.memory.add_message(role="assistant", content=result["answer"])

        return result

# Usage - conversation persists across sessions
agent = ConversationalAgent(config, db)
result1 = agent.ask("What is AI?")
result2 = agent.ask("Can you elaborate?")  # Uses history from previous question

# Restart - history preserved
agent2 = ConversationalAgent(config, db)
result3 = agent2.ask("What did we discuss?")  # Remembers previous conversation
```

**Production Metrics:**
- 28 E2E tests with real database operations
- <1ms hot tier retrieval (p95)
- <50ms warm tier retrieval (p95)
- 10,000+ entries per agent (SQLite)
- Millions of entries (PostgreSQL)

**See:** `docs/guides/memory-and-learning-system.md` for complete documentation.

### 5. Planning Agents - Structured Workflow Orchestration

Two planning patterns for structured workflows with validation and iterative refinement.

**PlanningAgent - Plan Before You Act:**
```python
from kaizen.agents.specialized.planning import PlanningAgent, PlanningConfig

# Create planning agent with strict validation
agent = PlanningAgent(PlanningConfig(
    llm_provider="openai",
    model="gpt-4",
    max_plan_steps=5,              # Maximum steps in plan
    validation_mode="strict",       # Pre-execution validation (strict/warn/off)
    enable_replanning=True,         # Replan if validation fails
    plan_format="structured"        # structured/narrative
))

# Execute with three-phase workflow
result = agent.run(
    task="Create research report on quantum computing",
    context={"length": "2000 words", "audience": "technical"}
)

# Three phases automatically executed:
# 1. PLAN: Generate multi-step plan
# 2. VALIDATE: Check plan feasibility before execution
# 3. EXECUTE: Execute validated plan
```

**PEVAgent - Plan, Execute, Verify, Refine:**
```python
from kaizen.agents.specialized.pev import PEVAgent, PEVAgentConfig

# Create PEV agent with iterative refinement
agent = PEVAgent(PEVAgentConfig(
    llm_provider="openai",
    model="gpt-4",
    max_iterations=5,               # Maximum refinement cycles
    verification_strictness="medium", # low/medium/high
    enable_error_recovery=True,     # Auto-recover from failures
    early_stop_threshold=0.9        # Stop if quality > 0.9
))

# Execute with iterative refinement
result = agent.run(
    task="Generate production-ready code for API endpoint",
    context={"language": "python", "framework": "fastapi"}
)

# Four phases iteratively executed:
# 1. PLAN: Generate execution plan
# 2. EXECUTE: Execute plan
# 3. VERIFY: Check output quality (post-execution)
# 4. REFINE: Improve if verification fails (loop until verified or max_iterations)
```

**Pattern Comparison:**

| Pattern | Planning | Validation | Cycles | Best For |
|---------|----------|------------|--------|----------|
| **PlanningAgent** | Upfront | Pre-execution | 1 (or replan) | Structured workflows, research, compliance |
| **PEVAgent** | Initial | Post-execution | Multiple refine | Code generation, quality-critical tasks |

**Use Cases:**
- **PlanningAgent**: Research reports, compliance workflows, structured analysis
- **PEVAgent**: Code generation, content creation, iterative improvement

**Key Features:**
- Multi-step decomposition with dependency tracking
- Validation before (Planning) or after (PEV) execution
- Automatic replanning on failure
- Error recovery with retry logic
- Progress tracking and intermediate results

**See:** `docs/guides/planning-agents-guide.md` for complete documentation.

### 6. Meta-Controller Routing - Intelligent Task Delegation

A2A-based semantic capability matching for intelligent agent selection and routing.

**Quick Start:**
```python
from kaizen.orchestration.meta_controller import MetaController
from kaizen.orchestration.pipeline import Pipeline

# Create specialized agents
code_agent = CodeGenerationAgent(config)
data_agent = DataAnalystAgent(config)
writing_agent = WritingAgent(config)

# Create meta-controller with A2A semantic matching
meta_controller = MetaController(
    agents=[code_agent, data_agent, writing_agent],
    selection_strategy="semantic",  # A2A-based capability matching
    fallback_strategy="round_robin", # Fallback if no match
    enable_load_balancing=True
)

# Automatic agent selection based on task semantics
result = meta_controller.route_task(
    task="Analyze sales data and create visualization",
    context={"data_source": "database", "format": "dashboard"}
)
# Automatically selects data_agent (highest capability match)
```

**Router Pipeline Pattern:**
```python
# Router pattern with semantic routing
router = Pipeline.router(
    agents=[code_agent, data_agent, writing_agent],
    routing_strategy="semantic"  # A2A-based routing
)

# Execute - automatically routes to best agent
result = router.run(task="Generate Python code for API endpoint")
# Routes to code_agent

result2 = router.run(task="Write product description")
# Routes to writing_agent
```

**Selection Strategies:**
- **semantic**: A2A-based capability matching (recommended)
- **round_robin**: Simple load balancing
- **random**: Random selection
- **capability**: Explicit capability scoring

**Fallback Strategies:**
- **round_robin**: Try next agent in rotation
- **all**: Try all agents until success
- **fail**: Fail if no match found
- **default**: Use default agent

**Integration with Pipeline Patterns:**

Router pattern automatically integrates with 4 pipeline patterns:

1. **Router**: Direct semantic routing
2. **Ensemble**: Agent discovery (select top-k agents for task)
3. **Supervisor-Worker**: Semantic worker selection
4. **Blackboard**: Dynamic specialist selection

**Example - Ensemble with A2A Discovery:**
```python
# Ensemble pattern with A2A agent discovery
ensemble = Pipeline.ensemble(
    agents=[code_expert, data_expert, writing_expert, research_expert],
    synthesizer=synthesis_agent,
    discovery_mode="a2a",  # Use A2A to find relevant agents
    top_k=3                # Select top 3 agents for task
)

# Execute - automatically discovers and selects best 3 agents
result = ensemble.run(
    task="Analyze codebase and suggest improvements"
)
# Discovers: code_expert (0.95), research_expert (0.82), data_expert (0.71)
# Executes with top 3, synthesizes results
```

**Key Features:**
- No hardcoded if/else routing logic (semantic matching)
- Automatic capability discovery via A2A protocol
- Load balancing and fallback strategies
- Performance tracking per agent
- Multi-criteria ranking (capability + availability + cost)

**Use Cases:**
- Multi-specialist task delegation
- Dynamic agent selection based on task requirements
- Load-balanced agent pools
- Hierarchical agent coordination

**See:** `docs/guides/meta-controller-routing-guide.md` for complete documentation.

---

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

4. **Multi-Agent Coordination** (`src/kaizen/orchestration/`)
   - Google A2A protocol integration (100% compliant)
   - SupervisorWorkerPattern with semantic matching (production-ready)
   - 4 additional patterns: Consensus, Debate, Sequential, Handoff
   - Automatic capability discovery, no hardcoded selection
   - Pipeline infrastructure for composable workflows

5. **Observability Stack** (`src/kaizen/core/autonomy/observability/`)
   - Distributed tracing: OpenTelemetry + Jaeger
   - Metrics collection: Prometheus with percentiles
   - Structured logging: JSON for ELK Stack
   - Audit trails: Immutable JSONL for compliance
   - Production-validated: -0.06% overhead, zero impact

6. **Lifecycle Infrastructure** (`src/kaizen/core/autonomy/`)
   - Hooks: Event-driven monitoring (6 builtin hooks)
   - State: Persistent checkpoints with pluggable storage
   - Interrupts: Graceful execution control (6 signal types)
   - Thread-safe, composable, extensible
   - 281 tests passing
7. **Permission System** (`src/kaizen/core/autonomy/permissions/`)
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

# Run E2E tests for autonomous agents (Ollama - FREE)
pytest tests/e2e/autonomy/ -v
```

### E2E Testing for Autonomous Agents

**E2E tests validate complete autonomous workflows with real infrastructure:**

**What E2E Tests Validate:**
- ✅ **Real LLM inference** using Ollama llama3.2:1b (FREE, no API costs)
- ✅ **Real database** operations with DataFlow (SQLite/PostgreSQL)
- ✅ **Real tools** execution (file system, HTTP, bash commands)
- ✅ **Complete workflows** end-to-end with NO MOCKING

**Prerequisites:**
```bash
# Install Ollama (first time only)
# macOS:
brew install ollama

# Linux:
curl -fsSL https://ollama.ai/install.sh | sh

# Windows: Download from https://ollama.ai

# Start Ollama service
ollama serve

# Pull model (first time only)
ollama pull llama3.2:1b
```

**Running E2E Tests:**
```bash
# Run all E2E tests
pytest tests/e2e/autonomy/ -v

# Run specific autonomy system
pytest tests/e2e/autonomy/test_tool_calling_e2e.py -v       # Tool calling
pytest tests/e2e/autonomy/test_planning_e2e.py -v           # Planning agents
pytest tests/e2e/autonomy/test_meta_controller_e2e.py -v    # Meta-controller
pytest tests/e2e/autonomy/test_memory_e2e.py -v             # Memory system
pytest tests/e2e/autonomy/checkpoints/ -v                   # Checkpoint system
```

**Writing E2E Tests:**

```python
import pytest
from kaizen.agents.autonomous.base import BaseAutonomousAgent
from kaizen.agents.autonomous.config import AutonomousConfig
from kaizen.signatures import Signature, InputField, OutputField

class TaskSignature(Signature):
    task: str = InputField(description="Task to perform")
    result: str = OutputField(description="Task result")

@pytest.mark.e2e  # Mark as E2E test
@pytest.mark.asyncio  # Async test
async def test_autonomous_workflow():
    """Test autonomous agent with real LLM and infrastructure."""

    # 1. Create config with Ollama (FREE)
    config = AutonomousConfig(
        llm_provider="ollama",
        model="llama3.2:1b",
        enable_interrupts=True,
        checkpoint_on_interrupt=True
    )

    # 2. Create agent
    agent = BaseAutonomousAgent(config=config, signature=TaskSignature())

    # 3. Execute with real LLM
    result = await agent.run_autonomous(task="Analyze data file")

    # 4. Validate results
    assert result is not None
    assert "result" in result
    assert len(result["result"]) > 0
```

**Key E2E Testing Patterns:**

1. **Always use Ollama** for E2E tests (FREE, no API costs)
2. **Always mark with @pytest.mark.e2e** for test discovery
3. **Always use real infrastructure** (NO MOCKING)
4. **Always clean up** resources in teardown

**Available E2E Test Suites:**

| Test Suite | File | Tests | What It Validates |
|------------|------|-------|-------------------|
| **Tool Calling** | `test_tool_calling_e2e.py` | 4 | File/HTTP/bash tools with permission policies and approval workflows |
| **Planning** | `test_planning_e2e.py` | 3 | Planning/PEV/ToT agents with multi-step decomposition |
| **Meta-Controller** | `test_meta_controller_e2e.py` | 3 | Semantic routing, fallback strategies, task decomposition |
| **Memory** | `test_memory_e2e.py` | 4 | Hot/warm/cold tier persistence, multi-hour conversations |
| **Checkpoints** | `checkpoints/` | 3 | Auto-checkpoint creation, resume from checkpoint, compression |

**Cost Analysis:**

**E2E Tests Cost**: $0.00
- Ollama LLM: FREE (local inference)
- SQLite: FREE (local database)
- No API calls to paid services

If using OpenAI for quality validation:
- Use `gpt-4o-mini` ($0.15/1M input, $0.60/1M output)
- Budget: <$20 for full E2E suite
- Cost tracking built into tests

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
