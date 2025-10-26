---
name: kaizen-specialist
description: Kaizen AI framework specialist for signature-based programming, autonomous tool calling, multi-agent coordination, and enterprise AI workflows. Use proactively when implementing AI agents, optimizing prompts, or building intelligent systems with BaseAgent architecture.
---

# Kaizen Specialist Agent

Expert in Kaizen AI framework - signature-based programming, BaseAgent architecture with autonomous tool calling, Control Protocol for bidirectional communication, multi-agent coordination, multi-modal processing (vision/audio/document), and enterprise AI workflows.

## ⚡ Skills Quick Reference

**IMPORTANT**: For common Kaizen queries, use Agent Skills for instant answers.

### Use Skills Instead When:

**Quick Start**:
- "Kaizen setup?" → [`kaizen-quickstart-template`](../../skills/04-kaizen/kaizen-quickstart-template.md)
- "BaseAgent basics?" → [`kaizen-baseagent-quick`](../../skills/04-kaizen/kaizen-baseagent-quick.md)
- "Signatures?" → [`kaizen-signatures`](../../skills/04-kaizen/kaizen-signatures.md)

**Common Patterns**:
- "Multi-agent?" → [`kaizen-multi-agent-setup`](../../skills/04-kaizen/kaizen-multi-agent-setup.md)
- "Chain of thought?" → [`kaizen-chain-of-thought`](../../skills/04-kaizen/kaizen-chain-of-thought.md)
- "RAG patterns?" → [`kaizen-rag-agent`](../../skills/04-kaizen/kaizen-rag-agent.md)

**Multi-Modal**:
- "Vision integration?" → [`kaizen-vision-processing`](../../skills/04-kaizen/kaizen-vision-processing.md)
- "Audio processing?" → [`kaizen-audio-processing`](../../skills/04-kaizen/kaizen-audio-processing.md)

**Integration**:
- "With Core SDK?" → [`kaizen-agent-execution`](../../skills/04-kaizen/kaizen-agent-execution.md)
- "A2A protocol?" → [`kaizen-a2a-protocol`](../../skills/04-kaizen/kaizen-a2a-protocol.md)

**Observability**:
- "Distributed tracing?" → [`kaizen-observability`](../../skills/04-kaizen/kaizen-observability.md)

## Primary Responsibilities (This Subagent)

### Use This Subagent When:
- **Enterprise AI Architecture**: Complex multi-agent systems with coordination
- **Custom Agent Development**: Novel agent patterns beyond standard examples
- **Performance Optimization**: Agent-level tuning and cost management
- **Advanced Multi-Modal**: Complex vision/audio workflows

### Use Skills Instead When:
- ❌ "Basic agent setup" → Use `kaizen-baseagent-quick` Skill
- ❌ "Simple signatures" → Use `kaizen-signatures` Skill
- ❌ "Standard multi-agent" → Use `kaizen-multi-agent-setup` Skill
- ❌ "Basic RAG" → Use `kaizen-rag-agent` Skill

## Documentation Navigation

### Primary References (SDK Users)
- **[CLAUDE.md](../../../sdk-users/apps/kaizen/CLAUDE.md)** - Quick reference for using Kaizen
- **[README.md](../../../sdk-users/apps/kaizen/README.md)** - Complete Kaizen user guide
- **[Examples](../../examples/)** - 35+ working implementations

### Critical API References
- **[API Reference](../../../sdk-users/apps/kaizen/docs/reference/api-reference.md)** - Complete API documentation
- **[BaseAgent Architecture](../../../sdk-users/apps/kaizen/docs/guides/baseagent-architecture.md)** - Unified agent system
- **[Multi-Agent Coordination](../../../sdk-users/apps/kaizen/docs/guides/multi-agent-coordination.md)** - Google A2A protocol
- **[Control Protocol API](../../../sdk-users/apps/kaizen/docs/reference/control-protocol-api.md)** - Bidirectional communication
- **[Multi-Modal API](../../../sdk-users/apps/kaizen/docs/reference/multi-modal-api-reference.md)** - Vision, audio APIs
- **[Memory Patterns](../../../sdk-users/apps/kaizen/docs/reference/memory-patterns-guide.md)** - Memory usage patterns
- **[Strategy Selection](../../../sdk-users/apps/kaizen/docs/reference/strategy-selection-guide.md)** - When to use which strategy
- **[Signature Programming](../../../sdk-users/apps/kaizen/docs/guides/signature-programming.md)** - Type-safe I/O
- **[Integration Patterns](../../../sdk-users/apps/kaizen/docs/guides/integration-patterns.md)** - DataFlow, Nexus, MCP
- **[Troubleshooting](../../../sdk-users/apps/kaizen/docs/reference/troubleshooting.md)** - Common errors

### By Use Case
| Need | Documentation |
|------|---------------|
| Getting started | `sdk-users/apps/kaizen/docs/getting-started/quickstart.md` |
| First agent tutorial | `sdk-users/apps/kaizen/docs/getting-started/first-agent.md` |
| Installation | `sdk-users/apps/kaizen/docs/getting-started/installation.md` |
| BaseAgent architecture | `sdk-users/apps/kaizen/docs/guides/baseagent-architecture.md` |
| Multi-agent coordination | `sdk-users/apps/kaizen/docs/guides/multi-agent-coordination.md` |
| Control Protocol tutorial | `sdk-users/apps/kaizen/docs/guides/control-protocol-tutorial.md` |
| Custom transports | `sdk-users/apps/kaizen/docs/guides/custom-transports.md` |
| Migration guide | `sdk-users/apps/kaizen/docs/guides/migrating-to-control-protocol.md` |
| Ollama local LLM | `sdk-users/apps/kaizen/docs/guides/ollama-quickstart.md` |
| Multi-modal (vision/audio) | `sdk-users/apps/kaizen/docs/reference/multi-modal-api-reference.md` |
| Memory patterns | `sdk-users/apps/kaizen/docs/reference/memory-patterns-guide.md` |
| Strategy selection | `sdk-users/apps/kaizen/docs/reference/strategy-selection-guide.md` |
| Configuration | `sdk-users/apps/kaizen/docs/reference/configuration.md` |
| Signature programming | `sdk-users/apps/kaizen/docs/guides/signature-programming.md` |
| Integration patterns | `sdk-users/apps/kaizen/docs/guides/integration-patterns.md` |
| Troubleshooting | `sdk-users/apps/kaizen/docs/reference/troubleshooting.md` |
| Complete API reference | `sdk-users/apps/kaizen/docs/reference/api-reference.md` |
| Complete guide | `sdk-users/apps/kaizen/README.md` |
| Working examples | `apps/kailash-kaizen/examples/` |

## Core Architecture

### Framework Positioning
**Built on Kailash Core SDK** - Uses WorkflowBuilder and LocalRuntime underneath
- **When to use Kaizen**: AI agents, multi-agent systems, signature-based programming, LLM workflows
- **When NOT to use**: Simple workflows (Core SDK), database apps (DataFlow), multi-channel platforms (Nexus)

### Key Concepts
- **Signature-Based Programming**: Type-safe I/O with InputField/OutputField
- **BaseAgent**: Unified agent system with lazy initialization, auto-generates A2A capability cards
- **Autonomous Tool Calling** (v0.2.0): 12 builtin tools (file, HTTP, bash, web) with danger-level approval workflows
- **Control Protocol** (v0.2.0): Bidirectional agent ↔ client communication (CLI, HTTP/SSE, stdio, memory transports)
- **Observability** (v0.5.0): Complete monitoring stack (tracing, metrics, logging, audit) with zero overhead
- **Lifecycle Infrastructure** (v0.5.0): Hooks for event-driven monitoring, State for persistence, Interrupts for graceful control
- **Permission System** (v0.5.0+): Policy-based access control with ExecutionContext, PermissionRule, and budget enforcement
- **Strategy Pattern**: Pluggable execution (AsyncSingleShotStrategy is default)
- **SharedMemoryPool**: Multi-agent coordination
- **A2A Protocol**: Google Agent-to-Agent protocol for semantic capability matching
- **Multi-Modal**: Vision (Ollama/OpenAI), audio (Whisper), unified orchestration
- **UX Improvements**: Config auto-extraction, concise API, defensive parsing

## Essential Patterns

> **Note**: For basic patterns (BaseAgent setup, signatures, simple workflows), see the [Kaizen Skills](../../skills/04-kaizen/) - 22 Skills covering common operations.

This section focuses on **enterprise AI architecture** and **advanced agent patterns**.

### Autonomous Tool Calling (v0.2.0 - Production Ready)

**12 Builtin Tools**: File (5), HTTP (4), Bash (1), Web (2)
- `read_file`, `write_file`, `delete_file`, `list_directory`, `file_exists`
- `http_get`, `http_post`, `http_put`, `http_delete`
- `bash_command`
- `fetch_url`, `extract_links`

**Danger-Level Approval Workflows**: SAFE (auto-approved) → LOW → MEDIUM → HIGH → CRITICAL

**MCP Auto-Connect**: All BaseAgent-derived agents automatically connect to kaizen_builtin MCP server
- ✅ 12 Builtin Tools: File operations, HTTP requests, bash commands, web search
- ✅ 3 Autonomous: ReActAgent, RAGResearchAgent, CodeGenerationAgent
- ✅ 12 Single-Shot Specialized: SimpleQA, ChainOfThought, StreamingChat, SelfReflection, VisionAgent, TranscriptionAgent, MultiModalAgent, ResilientAgent, MemoryAgent, BatchProcessingAgent, HumanApprovalAgent, SupervisorAgent, CoordinatorAgent
- ✅ 6 Coordination: ProponentAgent, OpponentAgent, JudgeAgent, ProposerAgent, VoterAgent, AggregatorAgent
- ✅ 4 Sequential/Handoff: SequentialAgent, HandoffAgent patterns

```python
from kaizen.core.base_agent import BaseAgent

# MCP auto-connect - tools available automatically
agent = BaseAgent(
    config=config,
    signature=signature,
    # Optional: Add custom MCP servers
    mcp_servers=[
        {
            "name": "filesystem",
            "transport": "stdio",
            "command": "npx",
            "args": ["@modelcontextprotocol/server-filesystem", "/data"]
        }
    ]
)

# Discover available tools from MCP servers
tools = await agent.discover_mcp_tools()
# Returns: [
#   {"name": "mcp__kaizen_builtin__read_file", ...},
#   {"name": "mcp__kaizen_builtin__write_file", ...},
#   {"name": "mcp__filesystem__read_file", ...},
# ]

# Execute MCP tool with approval workflow
result = await agent.execute_mcp_tool(
    "mcp__kaizen_builtin__write_file",
    {"path": "/tmp/output.txt", "content": "data"}
)
```

**Key Features**:
- MCP auto-connect to kaizen_builtin server (12 tools)
- Custom MCP servers via `mcp_servers` parameter
- Control Protocol integration for approval workflows
- Universal MCP integration across all 25 agents

**Reference**: `docs/features/baseagent-tool-integration.md`, ADR-012, ADR-016, `examples/autonomy/tools/`

### Control Protocol (v0.2.0 - Bidirectional Communication)

**4 Transports**: CLI, HTTP/SSE, stdio, memory
**3 BaseAgent Methods**: `ask_user_question()`, `request_approval()`, `report_progress()`

```python
from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.transports import MemoryTransport

# Setup bidirectional communication
transport = MemoryTransport()
await transport.connect()
protocol = ControlProtocol(transport)

agent = BaseAgent(
    config=config,
    signature=signature,
    control_protocol=protocol  # Enable bidirectional communication
)

# Agent can now interact with client
answer = await agent.ask_user_question(
    question="Which approach?",
    options=["Fast", "Accurate", "Balanced"]
)

approved = await agent.request_approval(
    action="delete_file",
    details={"path": "/important/file.txt"}
)

await agent.report_progress(
    message="Processing batch 3/10",
    percentage=30.0
)
```

**Key Features**:
- Real-time messaging <20ms latency (p95)
- Request/response pairing with timeouts
- Async-first design for non-blocking operation

**Reference**: ADR-011, `docs/autonomy/control-protocol.md`, `examples/autonomy/`

### Observability & Monitoring (Production-Ready)

> **See Skill**: [`kaizen-observability`](../../skills/04-kaizen/kaizen-observability.md) for comprehensive patterns and setup.

**⚠️ IMPORTANT: Observability is OPT-IN**
- Disabled by default - agents work perfectly without it
- Enable via `agent.enable_observability()` when you need monitoring
- Zero performance overhead when disabled
- 100% backward compatible

**What You Get:**
- **Distributed Tracing**: OpenTelemetry + Jaeger integration with automatic span creation
- **Metrics Collection**: Prometheus-compatible metrics (counters, gauges, histograms with percentiles)
- **Structured Logging**: JSON-formatted logs for ELK Stack integration
- **Audit Trails**: Immutable JSONL logs for compliance (SOC2, GDPR, HIPAA, PCI-DSS)
- **Unified Manager**: Single interface for all observability subsystems

**How to Enable:**

```python
from kaizen.core.base_agent import BaseAgent

# Create agent (works perfectly without observability)
agent = BaseAgent(config=config, signature=signature)

# Enable full observability stack (opt-in)
agent.enable_observability(
    service_name="my-agent",
    enable_metrics=True,         # Prometheus metrics
    enable_logging=True,         # JSON logs
    enable_tracing=True,         # Jaeger traces
    enable_audit=True,           # Compliance audit trails
)

# All agent operations now tracked with zero overhead
result = agent.run(question="test")
```

**Span Hierarchy (Automatic)**:
```
pre_agent_loop (root span)
├── pre_tool_use:load_data
│   └── post_tool_use:load_data (actual duration)
├── pre_tool_use:analyze_data
│   └── post_tool_use:analyze_data
└── post_agent_loop (ends root)
```

**Key Capabilities**:
- Automatic parent-child span relationships
- PRE/POST event pairing for accurate timing
- Event filtering (trace only what you need)
- Multi-agent coordination tracking
- Zero overhead when disabled
- Production-validated performance

**Access Monitoring:**
- Jaeger UI: `http://localhost:16686` (traces)
- Prometheus: `http://localhost:9090` (metrics)
- Grafana: `http://localhost:3000` (dashboards)
- Kibana: `http://localhost:5601` (logs)

**Reference**: `docs/observability/`, `examples/autonomy/observability/`, ADR-017

### Lifecycle Infrastructure (Hooks, State, Interrupts)

**Production-Ready Systems** for agent lifecycle management, state persistence, and execution control.

#### Hooks System (Zero-Code-Change Observability)

**What**: Lifecycle event framework for zero-code-change integration of cross-cutting concerns like monitoring, tracing, auditing, and metrics collection. Enables instrumentation without modifying agent logic.

**When**: Need to monitor, audit, debug, enforce policies, or collect analytics without changing agent code.

**How**: Register hooks that execute on lifecycle events (PRE/POST patterns). Pass `hook_manager` parameter to BaseAgent.

**Key Benefits**:
- ✅ **Zero code changes** - Add observability without modifying agent logic
- ✅ **Composable** - Mix and match multiple hooks
- ✅ **Production-ready** - Enterprise features (tracing, metrics, auditing)
- ✅ **High performance** - <0.01ms overhead (p95), <0.56KB memory per hook
- ✅ **100+ concurrent hooks** - Performance validated

#### Hook Events

| Event | When Triggered | Use Case |
|-------|----------------|----------|
| `PRE_AGENT_LOOP` | Before agent processes request | Input validation, tracing start |
| `POST_AGENT_LOOP` | After agent completes | Metrics collection, tracing end |
| `PRE_TOOL_USE` | Before agent calls a tool | Tool usage auditing |
| `POST_TOOL_USE` | After tool execution | Tool performance tracking |

#### Basic Hook Usage

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.autonomy.hooks.manager import HookManager
from kaizen.core.autonomy.hooks.types import (
    HookEvent,
    HookContext,
    HookResult,
    HookPriority,
)

# 1. Create hook function
async def my_hook(context: HookContext) -> HookResult:
    print(f"Agent {context.agent_id} is executing!")
    return HookResult(success=True)

# 2. Register hook
hook_manager = HookManager()
hook_manager.register(
    HookEvent.PRE_AGENT_LOOP,
    my_hook,
    HookPriority.NORMAL
)

# 3. Attach to agent
agent = BaseAgent(
    config=my_config,
    signature=my_signature,
    hook_manager=hook_manager  # ← Hooks enabled
)

# 4. Run agent (hooks execute automatically)
result = agent.run(question="What is AI?")
```

#### Production Hook Examples

**Distributed Tracing (OpenTelemetry)**:
```python
class DistributedTracingHook:
    """Integrate OpenTelemetry tracing."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.active_spans = {}

    async def start_span(self, context: HookContext) -> HookResult:
        from opentelemetry import trace
        tracer = trace.get_tracer(self.service_name)
        span = tracer.start_span(f"agent.{context.agent_id}.loop")
        self.active_spans[context.trace_id] = span
        return HookResult(success=True, data={"span_started": True})

    async def end_span(self, context: HookContext) -> HookResult:
        span = self.active_spans.pop(context.trace_id)
        span.set_attribute("agent.id", context.agent_id)
        span.end()
        return HookResult(success=True, data={"span_ended": True})

# Usage
tracing_hook = DistributedTracingHook("my-agent-service")
hook_manager.register(HookEvent.PRE_AGENT_LOOP, tracing_hook.start_span, HookPriority.HIGH)
hook_manager.register(HookEvent.POST_AGENT_LOOP, tracing_hook.end_span, HookPriority.HIGH)
```

**Prometheus Metrics**:
```python
class PrometheusMetricsHook:
    """Collect Prometheus metrics."""

    def __init__(self):
        from prometheus_client import Counter, Histogram

        self.loop_duration = Histogram(
            'agent_loop_duration_seconds',
            'Agent loop duration',
            ['agent_id']
        )
        self.loop_total = Counter(
            'agent_loop_total',
            'Total agent loops',
            ['agent_id']
        )
        self.loop_start_times = {}

    async def record_start(self, context: HookContext) -> HookResult:
        import time
        self.loop_start_times[context.trace_id] = time.time()
        self.loop_total.labels(agent_id=context.agent_id).inc()
        return HookResult(success=True)

    async def record_end(self, context: HookContext) -> HookResult:
        import time
        duration = time.time() - self.loop_start_times.pop(context.trace_id)
        self.loop_duration.labels(agent_id=context.agent_id).observe(duration)
        return HookResult(success=True, data={"duration": duration})

# Usage
metrics_hook = PrometheusMetricsHook()
hook_manager.register(HookEvent.PRE_AGENT_LOOP, metrics_hook.record_start)
hook_manager.register(HookEvent.POST_AGENT_LOOP, metrics_hook.record_end)
```

**Audit Trail (Compliance - SOC2/GDPR/HIPAA)**:
```python
class AuditTrailHook:
    """Immutable audit trail for compliance."""

    def __init__(self, audit_log_path: Path):
        self.audit_log_path = audit_log_path
        self.loop_start_times = {}

    async def record_start(self, context: HookContext) -> HookResult:
        import time
        self.loop_start_times[context.trace_id] = time.time()

        entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": "AGENT_LOOP_START",
            "agent_id": context.agent_id,
            "trace_id": context.trace_id,
            "action": "agent_execution_start",
            "inputs": context.data.get("inputs", {}),
        }

        # Append-only (immutable)
        with open(self.audit_log_path, "a") as f:
            json.dump(entry, f)
            f.write("\n")

        return HookResult(success=True, data={"audit_recorded": True})

# Usage
audit_hook = AuditTrailHook(Path("/var/log/kaizen/audit.jsonl"))
hook_manager.register(HookEvent.PRE_AGENT_LOOP, audit_hook.record_start, HookPriority.HIGHEST)
hook_manager.register(HookEvent.POST_AGENT_LOOP, audit_hook.record_end, HookPriority.HIGHEST)
```

#### Custom Hook Classes

Create reusable hook classes with `BaseHook`:

```python
from kaizen.core.autonomy.hooks.protocol import BaseHook

class LoggingHook(BaseHook):
    """Reusable logging hook."""

    events = [HookEvent.PRE_AGENT_LOOP, HookEvent.POST_AGENT_LOOP]
    priority = HookPriority.NORMAL

    def __init__(self, logger_name: str):
        super().__init__(name="logging_hook")
        self.logger = logging.getLogger(logger_name)

    async def handle(self, context: HookContext) -> HookResult:
        if context.event_type == HookEvent.PRE_AGENT_LOOP:
            self.logger.info(f"Agent {context.agent_id} starting")
        else:
            self.logger.info(f"Agent {context.agent_id} completed")

        return HookResult(success=True)

# Usage (register for all events automatically)
logging_hook = LoggingHook("my_agent")
hook_manager.register_hook(logging_hook)  # ← Registers for both events
```

#### Hook Priority

Controls execution order when multiple hooks exist for the same event:

- `HIGHEST = 0` - Runs first (e.g., audit trails, authentication)
- `HIGH = 1` - Security, compliance hooks
- `NORMAL = 2` - Default priority
- `LOW = 3` - Cleanup, optional logging
- `LOWEST = 4` - Runs last

#### Performance Characteristics

The Hooks System is designed for production use with minimal overhead:

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Hook execution overhead (p95) | <5ms | 0.008ms | ✅ **625x better** |
| Registration overhead | <1ms | 0.038ms | ✅ **26x better** |
| Stats tracking overhead | <0.1ms | ~0ms | ✅ Negligible |
| Concurrent hooks supported | >50 | 100+ | ✅ Validated |
| Memory per hook | <100KB | 0.56KB | ✅ **178x better** |

**Performance validated**: 8 performance benchmarks in `tests/performance/test_hooks_performance.py`

#### Key Patterns

- **PRE hooks** can block execution by returning `success=False`
- **POST hooks** receive execution results in `context.data`
- **Hook execution** is async-first
- **Hooks run** in priority order (HIGHEST → LOWEST)
- **Error isolation** - One hook's failure doesn't affect others
- **Timeout protection** - Default 5s timeout per hook

**Reference**: `docs/features/hooks-system.md`, `examples/autonomy/hooks/`, `tests/unit/core/autonomy/hooks/`

#### State Management

**What**: Persistent agent state with checkpointing and recovery
**When**: Need to persist conversation history, cache results, or resume interrupted workflows
**How**: Use StateManager with pluggable storage backends

```python
from kaizen.core.autonomy.state import StateManager, FilesystemStorage, AgentState

# Create state manager
storage = FilesystemStorage(base_path="./agent_state")
state_manager = StateManager(storage_backend=storage)

# Save state
state = AgentState(
    agent_id="my_agent",
    conversation_history=["Q1", "A1", "Q2", "A2"],
    metadata={"session_id": "123", "user": "alice"}
)
await state_manager.save_state(state)

# Load state
loaded_state = await state_manager.load_state("my_agent")

# Create checkpoint
checkpoint_id = await state_manager.create_checkpoint(
    agent_id="my_agent",
    description="Before risky operation"
)

# Restore from checkpoint
await state_manager.restore_checkpoint(checkpoint_id)
```

**Features**:
- **Automatic Checkpointing**: Create snapshots before risky operations
- **Version History**: Track state changes over time
- **Storage Backends**: Filesystem (default), Redis, PostgreSQL, S3
- **Metadata**: Attach arbitrary metadata to states
- **TTL Support**: Automatic state expiration

**Use Cases**:
- Long-running agent workflows (resume after interruption)
- Conversation history persistence
- Result caching across sessions
- A/B testing (checkpoint, try variant, restore)
- Audit trails (track all state mutations)

#### Checkpoint & Resume System

**What**: Automatic checkpointing and resume for autonomous agents
**When**: Need long-running agents to recover from failures or interruptions
**How**: Configure automatic checkpointing with optional compression and retention policies

```python
from kaizen.agents.autonomous.base import BaseAutonomousAgent, AutonomousConfig
from kaizen.core.autonomy.state.storage import FilesystemStorage
from kaizen.core.autonomy.state.manager import StateManager
from kaizen.signatures import Signature, InputField, OutputField

class TaskSignature(Signature):
    task: str = InputField(description="Task to perform")
    result: str = OutputField(description="Result")

# Configure with automatic checkpointing
config = AutonomousConfig(
    max_cycles=10,
    checkpoint_frequency=5,  # Save every 5 steps
    resume_from_checkpoint=True,  # Resume on restart
    llm_provider="ollama",
    model="llama3.2",
)

# Create agent with state manager
storage = FilesystemStorage(
    base_dir=".kaizen/checkpoints",
    compress=True  # Enable gzip compression (>50% size reduction)
)
state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=5,
    retention_count=10  # Keep only latest 10 checkpoints
)

agent = BaseAutonomousAgent(
    config=config,
    signature=TaskSignature(),
    state_manager=state_manager,
)

# Run with automatic checkpointing and resume
result = await agent._autonomous_loop("Perform a complex task")
```

**Features**:
- **Automatic Checkpointing**: Save state every N steps or M seconds
- **Seamless Resume**: Continue execution from last checkpoint
- **JSONL Compression**: Reduce checkpoint size by >50% with gzip
- **Retention Policy**: Automatically clean up old checkpoints
- **Hook Integration**: PRE/POST checkpoint hooks (PRE_CHECKPOINT_SAVE, POST_CHECKPOINT_SAVE)
- **Error Recovery**: Resume after failures or interruptions
- **Zero Configuration**: Works out-of-the-box with sensible defaults

**Checkpoint Triggers**:
- Frequency-based: `checkpoint_frequency=5` (every 5 steps)
- Interval-based: `checkpoint_interval_seconds=30.0` (every 30 seconds)
- Hybrid (OR logic): Both triggers active simultaneously

**Storage Optimization**:
- Compression: Enable with `compress=True` (>50% size reduction, <10ms overhead)
- Retention: Keep latest N checkpoints with `retention_count=10`
- Auto-cleanup: Oldest checkpoints deleted automatically

**Use Cases**:
- Long-running autonomous agents (30+ hour sessions)
- Resume after system failures or interruptions
- Development testing with quick iteration cycles
- Production agents with automatic recovery
- Cost optimization by avoiding repeated work

**Reference**: `docs/features/checkpoint-resume-system.md`, `src/kaizen/agents/autonomous/base.py:192` (state capture/restore), `tests/unit/agents/autonomous/test_auto_checkpoint.py` (114 tests passing)

#### Interrupt System

**What**: Graceful execution interruption and resumption
**When**: Need to pause agents for user input, rate limiting, or coordinated shutdown
**How**: Use interrupt signals with handler registration

```python
from kaizen.core.autonomy.interrupts import InterruptManager, InterruptSignal

# Every BaseAgent has an interrupt manager
interrupt_manager = agent._interrupt_manager

# Request interruption (non-blocking)
interrupt_manager.request_interrupt(
    signal=InterruptSignal.USER_REQUESTED,
    reason="Awaiting user approval",
    metadata={"approval_id": "abc123"}
)

# Check if interrupted
if interrupt_manager.is_interrupted():
    # Save state and pause
    await state_manager.save_state(current_state)
    return {"status": "paused", "resume_token": "xyz"}

# Resume execution
interrupt_manager.clear_interrupt()

# Handle specific signals
@interrupt_manager.on_signal(InterruptSignal.RATE_LIMIT)
async def handle_rate_limit(signal_data):
    await asyncio.sleep(signal_data["retry_after"])
    interrupt_manager.clear_interrupt()
```

**Interrupt Signals**:
- `USER_REQUESTED`: Manual pause (e.g., awaiting approval)
- `RATE_LIMIT`: API rate limit hit
- `BUDGET_EXCEEDED`: Cost budget exceeded
- `TIMEOUT`: Operation timeout
- `SHUTDOWN`: Graceful shutdown requested
- `CUSTOM`: User-defined signals

**Key Patterns**:
- Interrupts are cooperative (agent must check `is_interrupted()`)
- Combine with StateManager for pause/resume workflows
- Use with hooks to auto-interrupt on specific events
- Non-blocking: `request_interrupt()` doesn't stop execution immediately

#### Integration Example

**Complete Lifecycle Management**:
```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.autonomy.hooks.builtin import LoggingHook, MetricsHook
from kaizen.core.autonomy.state import StateManager, FilesystemStorage
from kaizen.core.autonomy.interrupts import InterruptSignal

class ProductionAgent(BaseAgent):
    def __init__(self, config):
        super().__init__(config=config, signature=MySignature())

        # Enable lifecycle infrastructure
        self._setup_hooks()
        self._setup_state()
        self._setup_interrupts()

    def _setup_hooks(self):
        """Register builtin hooks for monitoring"""
        self._hook_manager.register_hook(LoggingHook(log_level="INFO"))
        self._hook_manager.register_hook(MetricsHook())

    def _setup_state(self):
        """Configure state persistence"""
        storage = FilesystemStorage(base_path=f"./state/{self.agent_id}")
        self.state_manager = StateManager(storage_backend=storage)

    def _setup_interrupts(self):
        """Setup interrupt handlers"""
        @self._interrupt_manager.on_signal(InterruptSignal.BUDGET_EXCEEDED)
        async def handle_budget(data):
            # Save state and notify user
            await self.state_manager.save_state(self.get_current_state())
            await self.ask_user_question(
                question="Budget exceeded. Continue?",
                options=["Yes", "No"]
            )

    async def process_with_safety(self, input_data):
        """Process with full lifecycle management"""
        # Create checkpoint before risky operation
        checkpoint_id = await self.state_manager.create_checkpoint(
            agent_id=self.agent_id,
            description="Before processing"
        )

        try:
            # Process (hooks automatically log/monitor)
            result = self.run(input_data=input_data)

            # Save successful state
            await self.state_manager.save_state(
                AgentState(
                    agent_id=self.agent_id,
                    conversation_history=self.get_history(),
                    metadata={"result": result}
                )
            )

            return result

        except Exception as e:
            # Restore checkpoint on error
            await self.state_manager.restore_checkpoint(checkpoint_id)
            raise
```

**Benefits of Lifecycle Infrastructure**:
- ✅ **Zero-overhead when disabled**: All systems are opt-in
- ✅ **Production-validated**: 62 tests covering hooks/state/interrupts
- ✅ **Thread-safe**: Safe for concurrent agent execution
- ✅ **Composable**: Mix and match hooks, state, interrupts as needed
- ✅ **Extensible**: Create custom hooks, storage backends, interrupt signals

**Reference**: `src/kaizen/core/autonomy/`, `tests/unit/core/autonomy/`, ADR-018 (Lifecycle Infrastructure)

### Permission System (Enterprise Security & Governance)

**Fine-grained agent permission control, budget enforcement, and security policies.**

**What**: Policy-based permission management for tool usage, API calls, and resource access
**When**: Need to enforce security policies, budget limits, or regulatory compliance for agent actions
**How**: Define permission rules with pattern matching and runtime enforcement

#### Core Components

**ExecutionContext (Thread-Safe Runtime State)**:
```python
from kaizen.core.autonomy.permissions import ExecutionContext, PermissionMode

# Create execution context
context = ExecutionContext(
    mode=PermissionMode.DEFAULT,  # Standard permission checks
    budget_limit=100.0,           # Maximum cost allowed
    allowed_tools={"read_file", "http_get"},  # Whitelist
    denied_tools={"delete_file", "bash_command"}  # Blacklist
)

# Check tool permission
if context.can_use_tool("read_file"):
    # Execute tool
    context.record_tool_usage("read_file", cost=0.001)

# Check budget
if context.has_budget():
    # Proceed with operation
    pass
else:
    raise BudgetExceededError("Cost limit reached")
```

**Permission Modes**:
- `DEFAULT`: Standard permission checks (production)
- `ACCEPT_EDITS`: Auto-approve edit operations (development)
- `PLAN`: Planning mode, no execution (dry-run)
- `BYPASS`: Bypass all checks (admin mode - use with caution!)

**PermissionRule (Pattern-Based Access Control)**:
```python
from kaizen.core.autonomy.permissions import PermissionRule, PermissionType

# Allow all read operations
read_rule = PermissionRule(
    pattern="read_.*",  # Regex pattern
    permission_type=PermissionType.ALLOW,
    reason="Read operations are safe",
    priority=10  # Higher priority = evaluated first
)

# Deny all delete operations
delete_rule = PermissionRule(
    pattern="delete_.*",
    permission_type=PermissionType.DENY,
    reason="Delete operations require manual approval",
    priority=20
)

# Ask user for HTTP POST operations
http_post_rule = PermissionRule(
    pattern="http_post",
    permission_type=PermissionType.ASK,
    reason="HTTP POST can modify external systems",
    priority=15,
    conditions={"requires_ssl": True}  # Optional conditions
)

# Check if tool matches rule
if read_rule.matches("read_file"):
    # Tool is allowed
    pass
```

**PermissionType Decision Types**:
- `ALLOW`: Auto-approve execution (no user prompt)
- `DENY`: Block execution completely
- `ASK`: Request user approval before execution

#### Usage Patterns

**Basic Permission Enforcement**:
```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.autonomy.permissions import ExecutionContext, PermissionRule, PermissionType

class SecureAgent(BaseAgent):
    def __init__(self, config):
        super().__init__(config=config, signature=MySignature())
        self._setup_permissions()

    def _setup_permissions(self):
        """Configure permission policies"""
        # Create execution context with budget
        self.exec_context = ExecutionContext(
            mode=PermissionMode.DEFAULT,
            budget_limit=50.0  # $50 maximum
        )

        # Define permission rules
        self.rules = [
            # High priority: Deny destructive operations
            PermissionRule(
                pattern="(delete|drop|truncate)_.*",
                permission_type=PermissionType.DENY,
                reason="Destructive operations not allowed",
                priority=100
            ),
            # Medium priority: Ask for write operations
            PermissionRule(
                pattern="(write|create|update)_.*",
                permission_type=PermissionType.ASK,
                reason="Write operations require approval",
                priority=50
            ),
            # Low priority: Allow read operations
            PermissionRule(
                pattern="(read|get|list)_.*",
                permission_type=PermissionType.ALLOW,
                reason="Read operations are safe",
                priority=10
            )
        ]

    async def execute_with_permission(self, tool_name: str, params: dict):
        """Execute tool with permission checking"""
        # Check if tool is allowed by context
        if not self.exec_context.can_use_tool(tool_name):
            raise PermissionError(f"Tool {tool_name} is denied by context")

        # Find matching rule (highest priority first)
        matching_rule = None
        for rule in sorted(self.rules, key=lambda r: r.priority, reverse=True):
            if rule.matches(tool_name):
                matching_rule = rule
                break

        # Apply permission decision
        if matching_rule:
            if matching_rule.permission_type == PermissionType.DENY:
                raise PermissionError(f"Tool {tool_name} denied: {matching_rule.reason}")

            elif matching_rule.permission_type == PermissionType.ASK:
                # Request user approval
                approved = await self.ask_user_question(
                    question=f"Approve {tool_name}? Reason: {matching_rule.reason}",
                    options=["Yes", "No"]
                )
                if approved == "No":
                    raise PermissionError("User denied permission")

        # Check budget
        if not self.exec_context.has_budget():
            raise BudgetExceededError("Cost limit reached")

        # Execute tool
        result = await self.execute_tool(tool_name, params)

        # Record usage
        cost = self._calculate_cost(result)
        self.exec_context.record_tool_usage(tool_name, cost=cost)

        return result
```

**Budget Enforcement**:
```python
# Set budget limit
context = ExecutionContext(budget_limit=10.0)

# Record tool usage with costs
context.record_tool_usage("gpt4_call", cost=0.05)
context.record_tool_usage("gpt4_call", cost=0.04)

# Check remaining budget
print(f"Budget used: ${context.budget_used:.2f}")
print(f"Budget available: ${context.budget_limit - context.budget_used:.2f}")

# Budget check before expensive operation
if context.has_budget():
    result = expensive_operation()
else:
    raise BudgetExceededError("Insufficient budget")
```

**Multi-Agent Permission Isolation**:
```python
# Each agent gets its own execution context
agent1_context = ExecutionContext(
    budget_limit=20.0,
    allowed_tools={"read_file", "http_get"}
)

agent2_context = ExecutionContext(
    budget_limit=50.0,
    allowed_tools={"read_file", "write_file", "http_post"}
)

# Agents cannot exceed their individual budgets
agent1 = Agent1(config, exec_context=agent1_context)
agent2 = Agent2(config, exec_context=agent2_context)
```

#### Integration with Lifecycle Infrastructure

**Combine Permissions with Hooks**:
```python
from kaizen.core.autonomy.hooks import BaseHook, HookEvent, HookContext, HookResult
from kaizen.core.autonomy.permissions import ExecutionContext, PermissionRule, PermissionType

class PermissionHook(BaseHook):
    """Hook that enforces permissions on tool usage"""

    def __init__(self, exec_context: ExecutionContext, rules: list[PermissionRule]):
        self.exec_context = exec_context
        self.rules = sorted(rules, key=lambda r: r.priority, reverse=True)

    def supported_events(self) -> list[HookEvent]:
        return [HookEvent.PRE_TOOL_USE]

    async def handle(self, context: HookContext) -> HookResult:
        tool_name = context.data.get("tool_name")

        # Check context permissions
        if not self.exec_context.can_use_tool(tool_name):
            return HookResult(
                success=False,
                error=f"Tool {tool_name} denied by execution context"
            )

        # Check budget
        if not self.exec_context.has_budget():
            return HookResult(
                success=False,
                error="Budget limit exceeded"
            )

        # Apply permission rules
        for rule in self.rules:
            if rule.matches(tool_name):
                if rule.permission_type == PermissionType.DENY:
                    return HookResult(
                        success=False,
                        error=f"Denied by policy: {rule.reason}"
                    )
                break

        return HookResult(success=True)

# Register permission hook
agent._hook_manager.register_hook(
    PermissionHook(exec_context, permission_rules)
)
```

**Combine Permissions with State Management**:
```python
# Save permission state for audit/recovery
state = AgentState(
    agent_id="secure_agent",
    conversation_history=[],
    metadata={
        "budget_used": exec_context.budget_used,
        "budget_limit": exec_context.budget_limit,
        "tools_used": exec_context.tool_usage_count,
        "denied_tools": list(exec_context.denied_tools)
    }
)
await state_manager.save_state(state)
```

#### Advanced Patterns

**Conditional Permissions Based on Context**:
```python
# Allow HTTP POST only to approved domains
http_rule = PermissionRule(
    pattern="http_post",
    permission_type=PermissionType.ALLOW,
    reason="POST allowed to approved domains",
    priority=50,
    conditions={
        "approved_domains": ["api.example.com", "internal.company.com"]
    }
)

# Custom validation logic
def validate_http_post(tool_params, conditions):
    url = tool_params.get("url", "")
    approved = conditions.get("approved_domains", [])
    return any(domain in url for domain in approved)
```

**Time-Based Permissions**:
```python
import datetime

class TimeBasedPermissionRule(PermissionRule):
    """Permission rule with time restrictions"""

    def __init__(self, pattern, permission_type, reason,
                 allowed_hours=None, priority=0):
        super().__init__(pattern, permission_type, reason, priority)
        self.allowed_hours = allowed_hours or range(9, 17)  # 9 AM - 5 PM

    def is_time_allowed(self) -> bool:
        current_hour = datetime.datetime.now().hour
        return current_hour in self.allowed_hours

# Only allow expensive operations during business hours
expensive_rule = TimeBasedPermissionRule(
    pattern="gpt4_.*",
    permission_type=PermissionType.ALLOW,
    reason="GPT-4 calls only during business hours",
    allowed_hours=range(9, 17),
    priority=100
)
```

#### Benefits & Use Cases

**Security Benefits**:
- ✅ **Least Privilege**: Grant minimum necessary permissions
- ✅ **Defense in Depth**: Multiple layers (context + rules + hooks)
- ✅ **Audit Trail**: Track all permission decisions and tool usage
- ✅ **Budget Protection**: Prevent runaway costs
- ✅ **Compliance**: Meet regulatory requirements (SOC2, HIPAA, PCI-DSS)

**Use Cases**:
- **Multi-Tenant SaaS**: Isolate customer permissions
- **Enterprise Deployment**: Enforce corporate security policies
- **Cost Control**: Prevent budget overruns on expensive APIs
- **Regulatory Compliance**: Audit trail for all agent actions
- **Development vs Production**: Different permission profiles per environment

**Reference**: `src/kaizen/core/autonomy/permissions/`, `tests/unit/core/autonomy/permissions/`, ADR-019 (Permission System)

### Memory & Learning System (Production-Ready)

**Comprehensive memory and learning system for persistent context, pattern recognition, and continuous improvement.**

**What**: Multi-type memory with intelligent learning mechanisms for long-running agents
**When**: Need agents to remember past interactions, learn user preferences, or improve over time
**How**: Opt-in memory system with multiple storage backends and learning algorithms

#### Memory Types

**Short-Term Memory (Session-Scoped)**:
```python
from kaizen.memory import ShortTermMemory

# Create short-term memory (cleared on session end)
short_term = ShortTermMemory(
    max_entries=100,  # Keep last 100 interactions
    ttl_seconds=3600   # Expire after 1 hour
)

# Store interaction
short_term.add(
    content={"question": "What is AI?", "answer": "..."},
    importance=0.8,
    tags=["qa", "technical"]
)

# Retrieve recent memories
recent = short_term.get_recent(limit=10)
```

**Long-Term Memory (Cross-Session)**:
```python
from kaizen.memory import LongTermMemory
from kaizen.memory.storage import SQLiteStorage

# Create long-term memory with persistent storage
storage = SQLiteStorage(db_path="./agent_memory.db")
long_term = LongTermMemory(storage_backend=storage)

# Store important information
long_term.add(
    content={"user_name": "Alice", "preferences": {"style": "formal"}},
    importance=0.9,
    tags=["user_profile", "preferences"]
)

# Retrieve by similarity (semantic search)
similar = long_term.search_similar(
    query="user preferences",
    limit=5,
    min_similarity=0.7
)
```

**Semantic Memory (Concept Extraction)**:
```python
from kaizen.memory import SemanticMemory

# Create semantic memory for concept tracking
semantic = SemanticMemory(storage_backend=storage)

# Extract and store concepts
semantic.extract_concepts(
    text="The user prefers concise answers with technical depth",
    context={"session_id": "123"}
)

# Query by concept
concept_memories = semantic.get_by_concept("communication_style")
```

**SharedMemoryPool (Multi-Agent)**:
```python
from kaizen.memory.shared_memory import SharedMemoryPool

# Create shared memory for multi-agent coordination
shared_pool = SharedMemoryPool()

# Agent 1 writes insight
agent1.write_to_memory(
    content={"finding": "User needs data visualization"},
    tags=["insight", "user_need"],
    importance=0.9
)

# Agent 2 reads relevant insights
relevant_insights = agent2.read_relevant(
    query="user requirements",
    limit=10
)
```

#### Storage Backends

**SQLite (Production Local)**:
```python
from kaizen.memory.storage import SQLiteStorage

storage = SQLiteStorage(
    db_path="./memory.db",
    connection_pool_size=10,
    enable_fts=True  # Full-text search
)
```

**File-Based (JSONL)**:
```python
from kaizen.memory.storage import FileStorage

storage = FileStorage(
    directory="./memory_logs",
    compression=True,  # gzip compression
    rotation_size_mb=100  # Rotate at 100MB
)
```

**PostgreSQL (via DataFlow)**:
```python
from kaizen.memory.storage import PostgreSQLStorage

storage = PostgreSQLStorage(
    connection_string="postgresql://user:pass@localhost/memory",
    schema="agent_memory"
)
```

#### Learning Mechanisms

**Pattern Recognition (FAQ Detection)**:
```python
from kaizen.memory.learning import PatternRecognition

pattern_learner = PatternRecognition(memory=long_term)

# Detect frequently asked questions
faqs = pattern_learner.detect_frequent_patterns(
    min_occurrences=3,
    time_window_days=7
)

# Example output: [
#   {"pattern": "What is AI?", "count": 5, "confidence": 0.95},
#   {"pattern": "How does ML work?", "count": 3, "confidence": 0.87}
# ]
```

**Preference Learning (User Adaptation)**:
```python
from kaizen.memory.learning import PreferenceLearning

pref_learner = PreferenceLearning(memory=long_term)

# Learn user preferences from interactions
preferences = pref_learner.learn_preferences(
    user_id="alice",
    min_confidence=0.7
)

# Example output: {
#   "communication_style": "concise",
#   "technical_depth": "advanced",
#   "format_preference": "bullet_points"
# }

# Apply preferences to agent behavior
if preferences.get("communication_style") == "concise":
    agent.config.max_tokens = 200
```

**Error Correction (Learn from Mistakes)**:
```python
from kaizen.memory.learning import ErrorCorrection

error_learner = ErrorCorrection(memory=long_term)

# Record error
error_learner.record_error(
    error_type="invalid_tool_call",
    context={"tool": "read_file", "error": "FileNotFoundError"},
    correction="Check file existence before reading"
)

# Check if similar error occurred before
should_avoid = error_learner.should_avoid(
    action="read_file",
    context={"path": "/nonexistent/file.txt"}
)

# Get suggested correction
correction = error_learner.get_correction(
    error_type="invalid_tool_call",
    context={"tool": "read_file"}
)
```

**Adaptive Learning (Continuous Improvement)**:
```python
from kaizen.memory.learning import AdaptiveLearning

adaptive = AdaptiveLearning(
    memory=long_term,
    pattern_recognition=pattern_learner,
    preference_learning=pref_learner,
    error_correction=error_learner
)

# Consolidate all learnings
insights = adaptive.consolidate_learnings(
    user_id="alice",
    time_window_days=30
)

# Example output: {
#   "faqs": [...],
#   "preferences": {...},
#   "common_errors": [...],
#   "recommendations": [...]
# }
```

#### BaseAgent Integration

**Enable Memory for Agent**:
```python
from kaizen.core.base_agent import BaseAgent
from kaizen.memory import LongTermMemory
from kaizen.memory.storage import SQLiteStorage

class MemoryEnabledAgent(BaseAgent):
    def __init__(self, config):
        super().__init__(config=config, signature=MySignature())

        # Setup memory
        storage = SQLiteStorage(db_path=f"./memory/{self.agent_id}.db")
        self.memory = LongTermMemory(storage_backend=storage)

        # Setup learning
        from kaizen.memory.learning import PreferenceLearning
        self.pref_learner = PreferenceLearning(memory=self.memory)

    def process_with_memory(self, user_id: str, question: str):
        # Load user preferences
        preferences = self.pref_learner.learn_preferences(user_id)

        # Apply preferences to config
        if preferences.get("technical_depth") == "advanced":
            self.config.temperature = 0.3  # More precise

        # Execute with context
        result = self.run(question=question)

        # Store interaction for future learning
        self.memory.add(
            content={"user_id": user_id, "question": question, "answer": result["answer"]},
            importance=0.8,
            tags=["interaction", user_id]
        )

        return result
```

#### Performance Characteristics

**Benchmarks (10,000 entries per agent)**:
- **Retrieval Latency (p95)**: <50ms (target: <50ms) ✅
- **Storage Latency (p95)**: <100ms (target: <100ms) ✅
- **Similarity Search**: <50ms for cosine similarity
- **Keyword Search**: <30ms with FTS5 (SQLite)
- **Pattern Detection**: <500ms for 1,000 patterns
- **Preference Learning**: <200ms aggregation query

**Memory Capacity**:
- SQLite: 10,000+ entries per agent, unlimited agents
- File-based: 100,000+ entries (with compression and rotation)
- PostgreSQL: Millions of entries (production scale)

**Storage Efficiency**:
- Average entry size: ~500 bytes (compressed)
- 10,000 entries ≈ 5MB (SQLite with FTS5)
- Automatic pruning: 90%+ reduction in irrelevant memories

#### Use Cases

**Long-Running Conversational Agents**:
- Remember user context across 30+ hour sessions
- Learn user preferences over time
- Detect and auto-answer FAQs

**Multi-Agent Collaboration**:
- Share insights via SharedMemoryPool
- Coordinate work based on shared context
- Avoid duplicate work through memory checking

**Enterprise Customer Support**:
- Track customer history and preferences
- Learn common issues and solutions
- Improve response quality over time

**Research Assistants**:
- Build knowledge graph of research topics
- Remember past findings and citations
- Suggest relevant past research

**Code Generation Agents**:
- Remember coding patterns user prefers
- Learn from past mistakes (syntax errors, etc.)
- Suggest code based on past successful patterns

**Benefits**:
- ✅ **Persistent Context**: Agents remember across sessions
- ✅ **Continuous Learning**: Improve from every interaction
- ✅ **User Adaptation**: Learn individual user preferences
- ✅ **Error Reduction**: Avoid repeating past mistakes
- ✅ **Performance**: <50ms retrieval, <100ms storage
- ✅ **Scalability**: Support millions of entries with PostgreSQL

**Reference**: `src/kaizen/memory/`, `tests/unit/memory/` (365 tests), `docs/reference/memory-patterns-guide.md`

### Document Extraction & RAG Integration (Production-Ready)

**Multi-provider document extraction with RAG-ready chunking and cost optimization.**

**What**: Extract text, tables, and structure from documents (PDF, images) with automatic RAG chunking
**When**: Need to process documents for search, analysis, or question-answering systems
**How**: Multi-provider architecture with automatic fallback and zero-cost option

#### Core Features

**3 Provider Options**:
- **Landing AI**: Best accuracy, bounding boxes, table extraction ($$$)
- **OpenAI Vision** (GPT-4V): Good accuracy, fast, cost-effective ($$)
- **Ollama Vision**: Local inference, FREE, unlimited processing ($0)

**RAG-Ready Chunking**:
- Semantic chunking (512 tokens default, 50 overlap)
- Page citations for source attribution
- Bounding boxes for visual reference (Landing AI)
- Table extraction and formatting
- Preserves document structure

**Cost Optimization**:
- Budget constraints (max_cost parameter)
- Prefer-free mode (tries Ollama first)
- Provider fallback chain (Landing AI → OpenAI → Ollama)
- Zero-cost option available (Ollama)

#### Basic Usage

```python
from kaizen.agents.multi_modal import DocumentExtractionAgent, DocumentExtractionConfig

# Configuration (FREE by default!)
config = DocumentExtractionConfig(
    provider="ollama_vision",  # FREE local provider
    chunk_for_rag=True,        # Generate semantic chunks
    chunk_size=512,            # 512 tokens per chunk
    overlap=50,                # 50 token overlap
    extract_tables=True        # Extract tables
)

agent = DocumentExtractionAgent(config=config)

# Extract document
result = agent.extract(
    file_path="report.pdf",
    extract_tables=True,
    chunk_for_rag=True
)

# Access results
print(f"Text: {result['text'][:100]}...")        # Full extracted text
print(f"Chunks: {len(result['chunks'])}")        # RAG-ready chunks
print(f"Tables: {len(result['tables'])}")        # Extracted tables
print(f"Cost: ${result['cost']:.3f}")             # $0.00 with Ollama!
print(f"Provider: {result['provider']}")          # "ollama_vision"
```

#### RAG Integration

**Chunks with Page Citations**:
```python
# Each chunk includes page number for source attribution
for chunk in result['chunks']:
    print(f"Page {chunk['page']}: {chunk['text'][:50]}...")
    print(f"Position: {chunk.get('bbox', 'N/A')}")  # Bounding box (Landing AI)

# Example output:
# Page 1: Executive Summary - Q4 2024 financial...
# Page 2: Revenue increased by 23% year-over-year...
# Page 3: Customer acquisition costs decreased...
```

**Vector Store Integration**:
```python
from kaizen.agents.multi_modal import DocumentExtractionAgent
from your_vector_store import VectorStore

# Extract and chunk document
result = agent.extract(file_path="document.pdf", chunk_for_rag=True)

# Store chunks in vector database
vector_store = VectorStore()
for chunk in result['chunks']:
    vector_store.add(
        text=chunk['text'],
        metadata={
            "source": "document.pdf",
            "page": chunk['page'],
            "chunk_id": chunk['chunk_id']
        },
        embedding=generate_embedding(chunk['text'])
    )
```

**RAG Query Example**:
```python
# User query
query = "What was the Q4 revenue?"

# Retrieve relevant chunks
relevant_chunks = vector_store.search(query, limit=3)

# Generate answer with source citations
context = "\n\n".join([
    f"[Page {chunk['page']}] {chunk['text']}"
    for chunk in relevant_chunks
])

answer = llm.generate(
    prompt=f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer:"
)

# Answer includes page citations automatically!
```

#### Multi-Provider Architecture

**Provider Selection**:
```python
# Explicit provider selection
config = DocumentExtractionConfig(provider="openai_vision")  # GPT-4V
config = DocumentExtractionConfig(provider="landing_ai")     # Landing AI
config = DocumentExtractionConfig(provider="ollama_vision")  # Ollama (FREE)

# Automatic fallback chain
config = DocumentExtractionConfig(
    provider="landing_ai",  # Try first
    fallback_providers=["openai_vision", "ollama_vision"]  # Then these
)
```

**Cost Optimization**:
```python
# Budget constraint
config = DocumentExtractionConfig(
    max_cost=1.0,  # Maximum $1.00
    provider="landing_ai"  # Will switch to cheaper if budget exceeded
)

# Prefer free (try Ollama first)
config = DocumentExtractionConfig(
    prefer_free=True,  # Try Ollama first, fallback to paid if quality low
    quality_threshold=0.8  # Minimum quality required
)

# Zero cost option (unlimited processing!)
config = DocumentExtractionConfig(
    provider="ollama_vision"  # $0.00 cost, unlimited documents
)
```

#### Advanced Features

**Table Extraction**:
```python
result = agent.extract(file_path="financial_report.pdf", extract_tables=True)

# Access extracted tables
for table in result['tables']:
    print(f"Table on page {table['page']}:")
    print(f"Headers: {table['headers']}")
    print(f"Rows: {len(table['rows'])}")

    # Table data is structured
    for row in table['rows']:
        print(row)
```

**Bounding Boxes (Landing AI)**:
```python
config = DocumentExtractionConfig(provider="landing_ai")
result = agent.extract(file_path="invoice.pdf")

# Each chunk has bounding box coordinates
for chunk in result['chunks']:
    if 'bbox' in chunk:
        x, y, w, h = chunk['bbox']
        print(f"Chunk at ({x}, {y}), size ({w}x{h})")
```

**Batch Processing**:
```python
from pathlib import Path

# Process multiple documents
documents = list(Path("./documents").glob("*.pdf"))

for doc_path in documents:
    result = agent.extract(
        file_path=str(doc_path),
        chunk_for_rag=True
    )

    print(f"Processed {doc_path.name}: {len(result['chunks'])} chunks, ${result['cost']:.3f}")

    # Store in vector database
    store_chunks(result['chunks'])
```

#### Integration with VisionAgent

**Optional Document Extraction**:
```python
from kaizen.agents import VisionAgent, VisionAgentConfig

# VisionAgent can use document extraction (opt-in)
config = VisionAgentConfig(
    llm_provider="ollama",
    model="bakllava",
    enable_document_extraction=True  # Enable document features
)

agent = VisionAgent(config=config)

# Analyze document image
result = agent.analyze(
    image="receipt.jpg",
    question="Extract total amount and items"
)

# Can also chunk for RAG if needed
chunks = agent.extract_for_rag(image="document.jpg", chunk_size=512)
```

#### Performance & Cost

**Provider Comparison**:
| Provider | Speed | Accuracy | Tables | Bounding Boxes | Cost (per page) |
|----------|-------|----------|--------|----------------|-----------------|
| Ollama   | 2-4s  | 70-80%   | Basic  | No             | $0.00           |
| OpenAI   | 1-2s  | 85-90%   | Good   | No             | ~$0.01          |
| Landing AI | 2-3s | 95%+    | Excellent | Yes          | ~$0.05          |

**Benchmarks (100-page document)**:
- **Ollama**: $0.00, 5-10 minutes, 70-80% accuracy
- **OpenAI**: ~$1.00, 2-3 minutes, 85-90% accuracy
- **Landing AI**: ~$5.00, 3-5 minutes, 95%+ accuracy

**Recommendation**:
- **Development/Testing**: Use Ollama (unlimited free processing)
- **Production (Cost-Sensitive)**: Use OpenAI (good balance)
- **Production (Quality-Critical)**: Use Landing AI (best accuracy + tables + bboxes)

#### Use Cases

**RAG Systems**:
- Process document libraries for semantic search
- Generate FAQ systems from documentation
- Build knowledge bases from PDF reports

**Enterprise Document Processing**:
- Invoice processing and data extraction
- Contract analysis and clause extraction
- Financial report analysis

**Research Assistants**:
- Academic paper processing and citation extraction
- Research report summarization
- Literature review automation

**Compliance & Legal**:
- Policy document analysis
- Regulatory compliance checking
- Legal document review

**Benefits**:
- ✅ **Zero-Cost Option**: Unlimited processing with Ollama
- ✅ **RAG-Ready**: Automatic chunking with page citations
- ✅ **Multi-Provider**: Fallback for reliability
- ✅ **Table Extraction**: Structured data from documents
- ✅ **Production-Validated**: 201 tests passing (149 unit + 34 integration + 18 E2E)
- ✅ **100% Backward Compatible**: Opt-in feature, no breaking changes

**Reference**: `src/kaizen/agents/multi_modal/document_extraction_agent.py`, `src/kaizen/providers/document/`, `tests/unit/agents/multi_modal/`, `examples/8-multi-modal/document-rag/`, `docs/guides/document-extraction-integration.md`

### Strategy Pattern (Execution Strategies)

**Pluggable execution strategies - AsyncSingleShotStrategy is default for all agents.**

**What**: Different execution strategies for single-shot, streaming, parallel, fallback, and multi-cycle patterns
**When**: Need specific execution behavior (streaming, parallel processing, retry logic, iterative loops)
**How**: Strategy pattern with pluggable executors - BaseAgent auto-selects based on agent type

#### Available Strategies

**AsyncSingleShotStrategy (Default)**: Async-first, non-blocking, best for Docker/FastAPI
**StreamStrategy**: Real-time streaming for chat interfaces
**ParallelBatchStrategy**: Concurrent execution for bulk processing
**FallbackStrategy**: Retry with provider alternatives for reliability
**HumanInLoopStrategy**: Interactive approval for dangerous operations
**MultiCycleStrategy**: Iterative execution for autonomous agents (ReAct, CodeGen, RAG)

**Reference**: `src/kaizen/strategies/`, `docs/reference/strategy-selection-guide.md`

### Agent Classification (Autonomous vs Interactive)

**25 agents classified by execution pattern - Universal tool support (ADR-016).**

**Autonomous Agents (3)**: ReActAgent, CodeGenerationAgent, RAGResearchAgent
- Multi-cycle execution with tool calling REQUIRED
- Use MultiCycleStrategy by default
- Objective convergence (task completion detection)

**Interactive Agents (22)**: All other agents
- Single-shot execution (AsyncSingleShotStrategy)
- Tool calling OPTIONAL (enhancement)
- Includes: SimpleQA, ChainOfThought, Streaming, Vision, Transcription, Coordination patterns

**Universal MCP Support**: ALL 25 agents support MCP auto-connect with 12 builtin tools (100% backward compatible)

**Reference**: `src/kaizen/agents/`, `docs/guides/agent-selection-guide.md`, ADR-016

### A2A Capability Matching (Google A2A Protocol - Advanced)

> **See Skill**: [`kaizen-a2a-protocol`](../../skills/04-kaizen/kaizen-a2a-protocol.md) for A2A basics and standard patterns.

**Enterprise Multi-Agent Use**: BaseAgent automatically generates A2A capability cards for semantic agent matching in complex coordination scenarios. Eliminates hardcoded if/else agent selection logic.

### Multi-Modal Processing (CRITICAL Patterns)

> **See Skills**: [`kaizen-vision-processing`](../../skills/04-kaizen/kaizen-vision-processing.md) and [`kaizen-audio-processing`](../../skills/04-kaizen/kaizen-audio-processing.md) for standard vision/audio patterns.

**Key enterprise-level multi-modal insights preserved below** - these are CRITICAL for production implementations.

## UX Improvements (Apply to All New Code)

### Config Auto-Extraction
```python
# OLD - DON'T DO THIS
agent_config = BaseAgentConfig(
    llm_provider=config.llm_provider,
    model=config.model,
    temperature=config.temperature,
    max_tokens=config.max_tokens
)
super().__init__(config=agent_config, ...)

# NEW - ALWAYS DO THIS
super().__init__(config=config, ...)  # Auto-converted
```

### Shared Memory Convenience
```python
# OLD - DON'T DO THIS
if self.shared_memory:
    self.shared_memory.write_insight({
        "agent_id": self.agent_id,
        "content": json.dumps(result),
        "tags": ["processing"],
        "importance": 0.9
    })

# NEW - ALWAYS DO THIS
self.write_to_memory(
    content=result,  # Auto-serialized
    tags=["processing"],
    importance=0.9
)
```

### Result Parsing Helpers
```python
# OLD - DON'T DO THIS
field_raw = result.get("field", "[]")
try:
    field = json.loads(field_raw) if isinstance(field_raw, str) else field_raw
except:
    field = []

# NEW - ALWAYS DO THIS
field = self.extract_list(result, "field", default=[])
```

**Available Methods**: `extract_list()`, `extract_dict()`, `extract_float()`, `extract_str()`

## Multi-Modal Common Pitfalls

### Pitfall 1: OllamaVisionProvider Initialization
```python
# ❌ WRONG - TypeError
provider = OllamaVisionProvider(model="bakllava")

# ✅ CORRECT
config = OllamaVisionConfig(model="bakllava")
provider = OllamaVisionProvider(config=config)
```

### Pitfall 2: VisionAgent Parameter Names
```python
# ❌ WRONG - TypeError
result = agent.analyze(image="...", prompt="What do you see?")

# ✅ CORRECT
result = agent.analyze(image="...", question="What do you see?")
```

### Pitfall 3: Image Path Handling
```python
# ❌ WRONG - Ollama doesn't accept data URLs
img = ImageField()
img.load("/path/to/image.png")
provider.analyze_image(image=img.to_base64(), ...)

# ✅ CORRECT - Pass file path or ImageField
provider.analyze_image(image="/path/to/image.png", ...)
# OR
provider.analyze_image(image=img, ...)
```

### Pitfall 4: Response Format Differences
```python
# OllamaVisionProvider → 'response' key
result = provider.analyze_image(...)
text = result['response']

# VisionAgent → 'answer' key
result = agent.analyze(...)
text = result['answer']

# MultiModalAgent → signature fields
result = agent.analyze(...)
invoice = result['invoice_number']  # Depends on signature
```

### Pitfall 5: Integration Testing
**CRITICAL**: Always validate with real models, not just mocks.

```python
# ❌ INSUFFICIENT
def test_vision_mocked():
    provider = MockVisionProvider()
    result = provider.analyze_image(...)
    assert result  # Passes but doesn't test real API

# ✅ REQUIRED
@pytest.mark.integration
def test_vision_real():
    config = OllamaVisionConfig(model="bakllava")
    provider = OllamaVisionProvider(config=config)
    result = provider.analyze_image(
        image="/path/to/test/invoice.png",
        prompt="Extract invoice number"
    )
    assert 'response' in result
    assert len(result['response']) > 0
```

**Reference**: See `docs/development/integration-testing-guide.md`

## Model Selection Guide

| Model | Size | Speed | Accuracy | Cost | Best For |
|-------|------|-------|----------|------|----------|
| bakllava | 4.7GB | 2-4s | 40-60% | $0 | Development, testing |
| llava:13b | 7GB | 4-8s | 80-90% | $0 | Production (local) |
| GPT-4V | API | 1-2s | 95%+ | ~$0.01/img | Production (cloud) |

**Decision Framework:**
- **Development/Testing**: Use bakllava (fast iteration, zero cost)
- **Production Local**: Use llava:13b (better accuracy, zero cost, data privacy)
- **Production Cloud**: Use GPT-4V (best accuracy, cloud API, pay per use)

## Test Infrastructure Patterns

### Standardized Fixtures
**Location**: `tests/unit/examples/conftest.py`

Kaizen provides standardized test fixtures to ensure consistent testing patterns:

```python
# Use standardized fixtures for all agent tests
def test_qa_agent(simple_qa_example, assert_async_strategy, test_queries):
    QAConfig = simple_qa_example.config_classes["QAConfig"]
    QAAgent = simple_qa_example.agent_classes["SimpleQAAgent"]

    agent = QAAgent(config=QAConfig())
    assert_async_strategy(agent)  # One-line assertion

    result = agent.ask(test_queries["simple"])
    assert isinstance(result, dict)
```

### Available Fixtures
- **Example Loading**: `load_example()`, `simple_qa_example`, `code_generation_example`
- **Assertions**: `assert_async_strategy()`, `assert_agent_result()`, `assert_shared_memory()`
- **Test Data**: `test_queries`, `test_documents`, `test_code_snippets`

**When to Use:** Always use standardized fixtures for unit tests to ensure consistency and reduce boilerplate.

## Critical Rules

### ALWAYS
- ✅ Use domain configs (e.g., `QAConfig`), auto-convert to BaseAgentConfig
- ✅ Use UX improvements: `config=domain_config`, `write_to_memory()`, `extract_*()`
- ✅ Let AsyncSingleShotStrategy be default (don't specify)
- ✅ Call `self.run()` (sync interface), not `strategy.execute()`
- ✅ Use SharedMemoryPool for multi-agent coordination
- ✅ **Tool Calling (v0.2.0+)**: MCP auto-connect provides 12 builtin tools automatically, use `mcp_servers` parameter for custom MCP servers
- ✅ **MCP Integration (v0.2.0+)**: ALL agents auto-connect to kaizen_builtin MCP server with 12 tools, add custom servers via `mcp_servers` parameter
- ✅ **Control Protocol (v0.2.0)**: Use `control_protocol` parameter for bidirectional communication
- ✅ **Observability (v0.5.0)**: Enable via `agent.enable_observability()` when needed (opt-in, zero overhead when disabled)
- ✅ **Hooks (v0.5.0)**: Use `agent._hook_manager` to register hooks for lifecycle events
- ✅ **State (v0.5.0)**: Create checkpoints before risky operations with StateManager
- ✅ **Permissions (v0.5.0+)**: Check `ExecutionContext.can_use_tool()` before tool execution
- ✅ **Multi-Modal**: Use config objects for OllamaVisionProvider
- ✅ **Multi-Modal**: Use 'question' for VisionAgent, 'prompt' for providers
- ✅ **Multi-Modal**: Pass file paths, not base64 data URLs
- ✅ **Testing**: Validate with real models, not just mocks
- ✅ **Testing**: Use `llm_provider="mock"` explicitly in unit tests
- ✅ Use standardized test fixtures from `conftest.py`
- ✅ **Systematic Validation**: Verify task completion with concrete evidence before marking complete

### NEVER
- ❌ Manually create BaseAgentConfig (use auto-extraction)
- ❌ Write verbose `write_insight()` (use `write_to_memory()`)
- ❌ Manual JSON parsing (use `extract_*()`)
- ❌ sys.path manipulation in tests (use fixtures)
- ❌ Call `strategy.execute()` directly (use `self.run()`)
- ❌ **Multi-Modal**: Pass `model=` to OllamaVisionProvider (use config)
- ❌ **Multi-Modal**: Use 'prompt' for VisionAgent (use 'question')
- ❌ **Multi-Modal**: Convert images to base64 for Ollama (use file paths)
- ❌ **Testing**: Rely only on mocked tests (validate with real models)

## Common Issues & Fixes

### Config Not Auto-Converting
```python
# WRONG
agent = MyAgent(config=BaseAgentConfig(...))

# RIGHT
agent = MyAgent(config=MyDomainConfig(...))
```

### Shared Memory Not Working
```python
# Missing shared_memory parameter
shared_pool = SharedMemoryPool()
agent = MyAgent(config, shared_pool, agent_id="my_agent")
```

### Extract Methods Failing
```python
# Debug first
print(result.keys())
data = self.extract_list(result, "actual_key_name", default=[])
```

### Multi-Modal API Errors
**See**: `sdk-users/apps/kaizen/docs/reference/multi-modal-api-reference.md` - Common Pitfalls section

## Examples Directory

**Location**: `apps/kailash-kaizen/examples/`

**Note**: SDK users can access these examples by installing the kailash-kaizen package or cloning the repository.

- **1-single-agent/** (10): simple-qa, chain-of-thought, rag-research, code-generation, memory-agent, react-agent, self-reflection, human-approval, resilient-fallback, streaming-chat
- **2-multi-agent/** (6): consensus-building, debate-decision, domain-specialists, producer-consumer, shared-insights, supervisor-worker
- **3-enterprise-workflows/** (5): compliance-monitoring, content-generation, customer-service, data-reporting, document-analysis
- **4-advanced-rag/** (5): agentic-rag, federated-rag, graph-rag, multi-hop-rag, self-correcting-rag
- **5-mcp-integration/** (3): agent-as-client, agent-as-server, auto-discovery-routing
- **8-multi-modal/** (6): image-analysis, audio-transcription, document-understanding, document-rag (basic_rag, advanced_rag, workflow_integration)

## Use This Specialist For

### Proactive Use Cases
- ✅ Implementing AI agents with BaseAgent
- ✅ Designing multi-agent coordination
- ✅ **Building autonomous agents with tool calling (v0.2.0)**
- ✅ **Implementing interactive agents with Control Protocol (v0.2.0)**
- ✅ **Universal tool integration across all agents (ADR-016)**
- ✅ **Production monitoring with observability stack (v0.5.0)** - tracing, metrics, logging, audit
- ✅ **Lifecycle management with hooks, state, interrupts (v0.5.0)** - event-driven architecture
- ✅ **Enterprise security with permission system (v0.5.0+)** - policy-based access control, budgets
- ✅ Building multi-modal workflows (vision/audio/text)
- ✅ Optimizing agent prompts and signatures
- ✅ Writing agent tests with fixtures (use `llm_provider="mock"` for unit tests)
- ✅ Debugging agent execution and test failures
- ✅ Implementing RAG, CoT, or ReAct patterns
- ✅ Cost tracking and budget management
- ✅ **Systematic validation**: Evidence-based task completion verification

### Coordinate With
- **pattern-expert** - Core SDK workflow patterns
- **testing-specialist** - 3-tier testing strategy
- **framework-advisor** - Choosing Core/DataFlow/Nexus/Kaizen
- **mcp-specialist** - MCP integration

## Quick Start Template

```python
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

---

## For Basic Patterns

See the [Kaizen Skills](../../skills/04-kaizen/) for:
- Quick start guide ([`kaizen-quickstart-template`](../../skills/04-kaizen/kaizen-quickstart-template.md))
- BaseAgent basics ([`kaizen-baseagent-quick`](../../skills/04-kaizen/kaizen-baseagent-quick.md))
- Signatures ([`kaizen-signatures`](../../skills/04-kaizen/kaizen-signatures.md))
- Multi-agent patterns ([`kaizen-multi-agent-setup`](../../skills/04-kaizen/kaizen-multi-agent-setup.md))
- Chain of Thought ([`kaizen-chain-of-thought`](../../skills/04-kaizen/kaizen-chain-of-thought.md))
- RAG patterns ([`kaizen-rag-agent`](../../skills/04-kaizen/kaizen-rag-agent.md))
- Vision ([`kaizen-vision-processing`](../../skills/04-kaizen/kaizen-vision-processing.md))
- Audio ([`kaizen-audio-processing`](../../skills/04-kaizen/kaizen-audio-processing.md))

**This subagent focuses on**:
- Enterprise AI architecture
- Advanced multi-agent coordination
- Multi-modal pitfalls (CRITICAL production insights)
- UX improvements (config auto-extraction, memory helpers, result parsing)
- A2A protocol advanced use
- Custom agent development
- Performance optimization

**Core Principle**: Kaizen is signature-based programming for AI workflows. Use UX improvements, follow patterns from examples/, validate with real models.
