# Kaizen API Reference

Complete API reference for the Kaizen Framework, providing detailed documentation for all classes, methods, and interfaces with production-ready code examples.

## Table of Contents

1. [Core Classes](#core-classes)
2. [Autonomy System API](#autonomy-system-api)
   - [Hooks System](#hooks-system)
   - [Checkpoint System](#checkpoint-system)
   - [Interrupt Mechanism](#interrupt-mechanism)
   - [Memory System](#memory-system)
3. [Planning Agents API](#planning-agents-api)
4. [Meta-Controller Routing API](#meta-controller-routing-api)
5. [Configuration Reference](#configuration-reference)
6. [Error Codes Reference](#error-codes-reference)
7. [Performance Reference](#performance-reference)
8. [Integration Patterns](#integration-patterns)

## Core Classes

### BaseAgent
**Unified agent system with lazy initialization**

```python
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.signatures import Signature, InputField, OutputField

class QASignature(Signature):
    """Type-safe input/output definition."""
    question: str = InputField(desc="User question")
    answer: str = OutputField(desc="Generated answer")
    confidence: float = OutputField(desc="Confidence score 0-1")

# Create agent with configuration
config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4",
    temperature=0.7,
    max_tokens=1000
)

agent = BaseAgent(config=config, signature=QASignature())

# Execute with type-safe inputs
result = agent.run(question="What is AI?")
print(result["answer"])  # Direct field access
print(result["confidence"])  # 0.0-1.0 score
```

**Key Methods:**

- `run(**inputs) -> dict`: Execute agent with signature-based inputs
- `to_a2a_card() -> dict`: Generate A2A capability card
- `to_workflow() -> WorkflowBuilder`: Convert to Kailash workflow

**Auto-Features:**

- Lazy initialization (workflows created on demand)
- Automatic A2A capability card generation
- Strategy pattern execution (AsyncSingleShotStrategy default)

### Signature
**Type-safe input/output definitions with field validation**

```python
from kaizen.signatures import Signature, InputField, OutputField
from typing import List, Optional

class AdvancedSignature(Signature):
    """Multi-field signature with validation."""

    # Input fields
    query: str = InputField(desc="User query", required=True)
    context: Optional[str] = InputField(desc="Additional context")
    complexity: int = InputField(desc="Complexity level 1-5")

    # Output fields
    response: str = OutputField(desc="Generated response")
    confidence: float = OutputField(desc="Confidence 0.0-1.0")
    citations: List[str] = OutputField(desc="Source citations")
    follow_ups: List[str] = OutputField(desc="Suggested follow-ups")

# Use with agent
agent = BaseAgent(config=config, signature=AdvancedSignature())
result = agent.run(
    query="Explain quantum computing",
    context="For high school students",
    complexity=3
)
```

**Field Types:**

- `InputField`: Input parameter definition
- `OutputField`: Output field definition
- Supports: `str`, `int`, `float`, `bool`, `dict`, `list`, `List[T]`, `Optional[T]`

### KaizenConfig
**Framework-level configuration with enterprise features**

```python
from kaizen.core.config import KaizenConfig

config = KaizenConfig(
    # Core settings
    signature_programming_enabled=True,
    performance_tracking=True,
    transparency_enabled=True,

    # Caching settings
    cache_enabled=True,
    cache_backend="memory",  # memory, redis, database
    cache_ttl=3600,

    # Monitoring settings
    monitoring_level="detailed",  # basic, detailed, comprehensive
    metrics_retention="7d",
    real_time_metrics=False,

    # Enterprise settings
    security_profile="enterprise",  # standard, enterprise
    audit_enabled=True,
    compliance_mode=True
)
```

## Autonomy System API

### Hooks System

**Event-driven observability with zero code changes**

#### HookManager

```python
from kaizen.core.autonomy.hooks import (
    HookManager,
    HookEvent,
    HookContext,
    HookResult,
    HookPriority
)

# Create hook manager
hook_manager = HookManager()

# Define hook handler
async def audit_hook(context: HookContext) -> HookResult:
    """Log all agent executions for compliance."""
    print(f"Agent {context.agent_id} executed at {context.timestamp}")
    print(f"Status: {context.metadata.get('status')}")
    return HookResult(success=True)

# Register hook with priority
hook_manager.register(
    event_type=HookEvent.POST_AGENT_LOOP,
    handler=audit_hook,
    priority=HookPriority.HIGH  # Execute before normal priority hooks
)

# Use with agent
agent = BaseAgent(
    config=config,
    signature=signature,
    hook_manager=hook_manager
)
```

**Available Events:**

| Event | When Triggered | Use Case |
|-------|----------------|----------|
| `PRE_AGENT_INIT` | Before agent initialization | Resource allocation |
| `POST_AGENT_INIT` | After agent initialization | Configuration validation |
| `PRE_AGENT_LOOP` | Before each execution cycle | Rate limiting, auth |
| `POST_AGENT_LOOP` | After each execution cycle | Logging, metrics |
| `PRE_TOOL_CALL` | Before tool execution | Permission checks |
| `POST_TOOL_CALL` | After tool execution | Result validation |
| `PRE_CHECKPOINT_SAVE` | Before checkpoint save | State validation |
| `POST_CHECKPOINT_SAVE` | After checkpoint save | Backup notification |
| `PRE_INTERRUPT` | Before interrupt handling | Cleanup tasks |
| `POST_INTERRUPT` | After interrupt handling | Recovery actions |

**HookPriority Levels:**

```python
from kaizen.core.autonomy.hooks import HookPriority

# Execution order (ascending)
HookPriority.CRITICAL  # value=1, first to execute
HookPriority.HIGH      # value=2
HookPriority.NORMAL    # value=3 (default)
HookPriority.LOW       # value=4
HookPriority.LOWEST    # value=5, last to execute
```

#### Production Hook Examples

**1. Audit Trail Hook:**

```python
from kaizen.core.autonomy.hooks import BaseHook, HookContext, HookResult

class AuditTrailHook(BaseHook):
    """Enterprise audit trail with PCI DSS compliance."""

    def __init__(self, audit_log_path: str):
        super().__init__(name="audit_trail")
        self.audit_log = audit_log_path
        self.events = [
            HookEvent.POST_AGENT_LOOP,
            HookEvent.POST_TOOL_CALL,
            HookEvent.POST_CHECKPOINT_SAVE
        ]

    async def handle(self, context: HookContext) -> HookResult:
        """Log all agent actions for forensic analysis."""
        log_entry = {
            "timestamp": context.timestamp,
            "agent_id": context.agent_id,
            "event": context.event.value,
            "user": context.metadata.get("user_id"),
            "action": context.metadata.get("action"),
            "result": context.metadata.get("result"),
        }

        # Write to tamper-proof audit log
        with open(self.audit_log, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

        return HookResult(success=True)

# Register audit hook
hook = AuditTrailHook("/var/log/kaizen/audit.log")
hook_manager.register_hook(hook, priority=HookPriority.CRITICAL)
```

**2. Distributed Tracing Hook:**

```python
from opentelemetry import trace
from opentelemetry.trace import SpanKind

class DistributedTracingHook(BaseHook):
    """OpenTelemetry integration for distributed tracing."""

    def __init__(self):
        super().__init__(name="distributed_tracing")
        self.tracer = trace.get_tracer("kaizen.agent")
        self.events = [
            HookEvent.PRE_AGENT_LOOP,
            HookEvent.POST_AGENT_LOOP,
        ]

    async def handle(self, context: HookContext) -> HookResult:
        """Create trace spans for agent execution."""
        if context.event == HookEvent.PRE_AGENT_LOOP:
            # Start span
            span = self.tracer.start_span(
                f"agent.{context.agent_id}",
                kind=SpanKind.INTERNAL
            )
            span.set_attribute("agent.id", context.agent_id)
            context.metadata["span"] = span

        elif context.event == HookEvent.POST_AGENT_LOOP:
            # End span
            span = context.metadata.get("span")
            if span:
                span.set_attribute("agent.status", context.metadata.get("status"))
                span.end()

        return HookResult(success=True)
```

**3. Prometheus Metrics Hook:**

```python
from prometheus_client import Counter, Histogram

class PrometheusMetricsHook(BaseHook):
    """Export Prometheus metrics for monitoring."""

    def __init__(self):
        super().__init__(name="prometheus_metrics")
        self.events = [HookEvent.POST_AGENT_LOOP, HookEvent.POST_TOOL_CALL]

        # Define metrics
        self.agent_executions = Counter(
            "kaizen_agent_executions_total",
            "Total agent executions",
            ["agent_id", "status"]
        )
        self.execution_duration = Histogram(
            "kaizen_agent_execution_duration_seconds",
            "Agent execution duration",
            ["agent_id"]
        )

    async def handle(self, context: HookContext) -> HookResult:
        """Record metrics for Prometheus scraping."""
        if context.event == HookEvent.POST_AGENT_LOOP:
            status = context.metadata.get("status", "unknown")
            self.agent_executions.labels(
                agent_id=context.agent_id,
                status=status
            ).inc()

            duration = context.metadata.get("duration_seconds", 0.0)
            self.execution_duration.labels(
                agent_id=context.agent_id
            ).observe(duration)

        return HookResult(success=True)
```

**Location:** `kaizen.core.autonomy.hooks`
**Examples:** `examples/autonomy/hooks/` (audit_trail, distributed_tracing, prometheus_metrics)
**Guide:** [Hooks System Guide](../guides/hooks-system-guide.md)

### Checkpoint System

**State persistence with save/load/fork operations**

#### StateManager

```python
from kaizen.core.autonomy.state import (
    StateManager,
    AgentState,
    FilesystemStorage,
    DatabaseStorage
)

# Setup state manager with filesystem storage
storage = FilesystemStorage(base_dir="./checkpoints")
state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=10,        # Every 10 steps
    checkpoint_interval=60.0,       # OR every 60 seconds
    retention_count=100,            # Keep last 100 checkpoints
    hook_manager=hook_manager       # Optional hooks integration
)

# Create agent state
agent_state = AgentState(
    agent_id="research_agent",
    step_number=0,
    status="running",
    conversation_history=[
        {"user": "Research AI ethics", "agent": "Starting research..."}
    ],
    memory_contents={"topic": "AI ethics", "papers_reviewed": 3},
    budget_spent_usd=0.15,
    metadata={"session_id": "session_123"}
)

# Save checkpoint
checkpoint_id = await state_manager.save_checkpoint(agent_state)
print(f"Checkpoint saved: {checkpoint_id}")
# Output: "Checkpoint saved: research_agent_step_10_20231025_120000"

# Load specific checkpoint
restored_state = await state_manager.load_checkpoint(checkpoint_id)

# Resume from latest checkpoint
latest_state = await state_manager.resume_from_latest("research_agent")

# Fork checkpoint (create independent branch)
forked_state = await state_manager.fork_from_checkpoint(
    checkpoint_id,
    new_agent_id="research_agent_fork1"
)
```

**Storage Backends:**

```python
# 1. Filesystem Storage (default)
from kaizen.core.autonomy.state import FilesystemStorage

storage = FilesystemStorage(
    base_dir="./checkpoints",
    compress=True  # gzip compression
)

# 2. Database Storage (PostgreSQL/SQLite via DataFlow)
from kaizen.core.autonomy.state import DatabaseStorage
from dataflow import DataFlow

db = DataFlow(database_url="postgresql://localhost/kaizen")
storage = DatabaseStorage(dataflow=db)
```

**AgentState Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `agent_id` | str | Unique agent identifier |
| `step_number` | int | Current execution step |
| `status` | str | Agent status (running, paused, completed) |
| `conversation_history` | list | Complete conversation turns |
| `memory_contents` | dict | Memory tier snapshots |
| `budget_spent_usd` | float | Total budget consumed |
| `metadata` | dict | Custom metadata fields |

**Location:** `kaizen.core.autonomy.state`
**Examples:** `examples/autonomy/lifecycle/`
**Guide:** [State Persistence Guide](../guides/state-persistence-guide.md)

### Interrupt Mechanism

**Graceful shutdown coordination with checkpoint integration**

#### InterruptManager

```python
from kaizen.core.autonomy.interrupts import (
    InterruptManager,
    InterruptSource,
    InterruptMode,
    InterruptReason
)
from kaizen.agents.autonomous import BaseAutonomousAgent, AutonomousConfig

# Enable interrupts in agent config
config = AutonomousConfig(
    llm_provider="openai",
    model="gpt-4",
    enable_interrupts=True,              # Enable interrupt handling
    graceful_shutdown_timeout=5.0,       # Max time for graceful shutdown
    checkpoint_on_interrupt=True         # Auto-save checkpoint before exit
)

# Create autonomous agent with interrupts
agent = BaseAutonomousAgent(config=config, signature=TaskSignature())

# Add timeout handler (auto-stop after 300 seconds)
from kaizen.core.autonomy.interrupts.handlers import TimeoutInterruptHandler

timeout_handler = TimeoutInterruptHandler(timeout_seconds=300.0)
agent.interrupt_manager.add_handler(timeout_handler)

# Run agent - handles Ctrl+C, timeouts, budget limits gracefully
try:
    result = await agent.run_autonomous(task="Analyze large dataset")
except InterruptedError as e:
    print(f"Agent interrupted: {e.reason.message}")
    print(f"Source: {e.reason.source}")  # USER, SYSTEM, or PROGRAMMATIC
    print(f"Mode: {e.reason.mode}")  # GRACEFUL or IMMEDIATE

    # Restore from checkpoint if needed
    checkpoint_id = e.reason.metadata.get("checkpoint_id")
    if checkpoint_id:
        restored_state = await state_manager.load_checkpoint(checkpoint_id)
```

**Interrupt Sources:**

```python
from kaizen.core.autonomy.interrupts import InterruptSource

# Three interrupt sources
InterruptSource.USER         # User-initiated (Ctrl+C, SIGINT, SIGTERM)
InterruptSource.SYSTEM       # System-initiated (timeout, budget, resources)
InterruptSource.PROGRAMMATIC # API-initiated (agent.interrupt(), hook)
```

**Interrupt Modes:**

```python
from kaizen.core.autonomy.interrupts import InterruptMode

# Two shutdown modes
InterruptMode.GRACEFUL   # Finish current cycle, save checkpoint (default)
InterruptMode.IMMEDIATE  # Stop immediately, may lose state
```

**Built-in Interrupt Handlers:**

```python
from kaizen.core.autonomy.interrupts.handlers import (
    TimeoutInterruptHandler,
    BudgetInterruptHandler,
    ResourceInterruptHandler,
)

# 1. Timeout Handler (stop after N seconds)
timeout = TimeoutInterruptHandler(timeout_seconds=300.0)
agent.interrupt_manager.add_handler(timeout)

# 2. Budget Handler (stop when budget exceeded)
budget = BudgetInterruptHandler(max_budget_usd=10.0)
agent.interrupt_manager.add_handler(budget)

# 3. Resource Handler (stop when memory/CPU exceeded)
resource = ResourceInterruptHandler(
    max_memory_mb=1000,
    max_cpu_percent=80.0
)
agent.interrupt_manager.add_handler(resource)
```

**Custom Interrupt Handler:**

```python
from kaizen.core.autonomy.interrupts import BaseInterruptHandler, InterruptReason

class CustomInterruptHandler(BaseInterruptHandler):
    """Custom interrupt logic."""

    def __init__(self, condition_check: Callable):
        self.condition_check = condition_check

    async def check_interrupt(self, context: dict) -> InterruptReason | None:
        """Check if interrupt condition met."""
        if await self.condition_check(context):
            return InterruptReason(
                source=InterruptSource.PROGRAMMATIC,
                mode=InterruptMode.GRACEFUL,
                message="Custom condition met",
                metadata={"context": context}
            )
        return None

# Use custom handler
handler = CustomInterruptHandler(lambda ctx: ctx.get("error_count") > 5)
agent.interrupt_manager.add_handler(handler)
```

**Location:** `kaizen.core.autonomy.interrupts`
**Examples:** `examples/autonomy/interrupts/` (ctrl_c, timeout, budget)
**Guide:** [Interrupt Mechanism Guide](../guides/interrupt-mechanism-guide.md)

### Memory System

**3-tier hierarchical storage with automatic promotion/demotion**

#### DataFlow Backend (Cold Tier)

```python
from kaizen.memory.backends import DataFlowBackend
from dataflow import DataFlow

# Setup DataFlow database
db = DataFlow(database_url="postgresql://localhost/kaizen")

@db.model
class ConversationMessage:
    """Persistent conversation storage."""
    id: str
    conversation_id: str
    sender: str  # "user" or "agent"
    content: str
    timestamp: str
    metadata: dict

# Create DataFlow backend for cold tier (< 100ms)
backend = DataFlowBackend(db, model_name="ConversationMessage")

# Save conversation turn
backend.save_turn(
    conversation_id="session_123",
    turn_data={
        "sender": "user",
        "content": "What is quantum computing?",
        "timestamp": "2023-10-25T12:00:00",
        "metadata": {"intent": "question"}
    }
)

# Load conversation history
turns = backend.load_turns(
    conversation_id="session_123",
    limit=10  # Last 10 turns
)

# Search conversations (semantic or keyword)
results = backend.search_conversations(
    query="quantum computing",
    limit=5
)

# Delete old conversations
deleted_count = backend.delete_conversation("session_123")
```

**Memory Tier Performance:**

| Tier | Latency Target | Storage Type | Capacity | Use Case |
|------|----------------|--------------|----------|----------|
| Hot | < 1ms | In-memory (dict) | 1K-10K items | Active session data |
| Warm | < 10ms | In-memory (LRU cache) | 10K-100K items | Recent conversations |
| Cold | < 100ms | Database (DataFlow) | Unlimited | Long-term history |

**Configuration:**

```python
from kaizen.memory.backends import DataFlowBackend, DataFlowConfig

config = DataFlowConfig(
    # Connection settings
    database_url="postgresql://localhost/kaizen",
    auto_migrate=True,

    # Performance settings
    batch_size=100,  # Bulk operations
    cache_enabled=True,
    cache_ttl=300,

    # Retention settings
    max_conversations=10000,
    max_turns_per_conversation=1000,
    auto_cleanup=True,
    cleanup_interval=3600  # 1 hour
)

backend = DataFlowBackend(db, model_name="ConversationMessage", config=config)
```

**Location:** `kaizen.memory.backends`
**Examples:** `examples/autonomy/memory/`

## Planning Agents API

### PlanningAgent

**Plan → Validate → Execute pattern**

```python
from kaizen.agents import PlanningAgent, PlanningConfig

# Create planning agent
config = PlanningConfig(
    llm_provider="openai",
    model="gpt-4",
    max_plan_steps=10,              # Maximum steps in plan
    validation_mode="strict",        # strict, warn, off
    enable_replanning=True,         # Retry if validation fails
    max_replanning_attempts=3
)

agent = PlanningAgent(config=config)

# Execute task with planning
result = agent.run(task="Create comprehensive research report on AI ethics")

# Access plan details
print(result["plan"])
# Output: [
#   {"step": 1, "action": "Research AI ethics principles"},
#   {"step": 2, "action": "Review case studies"},
#   {"step": 3, "action": "Synthesize findings"},
#   {"step": 4, "action": "Write report"}
# ]

print(result["validation_result"])
# Output: {"valid": True, "issues": [], "warnings": []}

print(result["execution_results"])
# Output: [
#   {"step": 1, "status": "completed", "output": "..."},
#   {"step": 2, "status": "completed", "output": "..."},
#   ...
# ]

print(result["final_result"])
# Output: "AI Ethics Report:\n\n1. Introduction\n..."
```

**Validation Modes:**

| Mode | Behavior | When to Use |
|------|----------|-------------|
| `strict` | Reject invalid plans, trigger replanning | Production, critical tasks |
| `warn` | Log warnings but continue execution | Development, experimental |
| `off` | No validation | Performance testing |

**Location:** `kaizen.agents.specialized.planning`
**Examples:** `examples/1-single-agent/planning-agent/`
**Guide:** [Planning Agents Guide](../guides/planning-agents-guide.md)

### PEVAgent

**Plan → Execute → Verify → Refine iterative loop**

```python
from kaizen.agents import PEVAgent, PEVConfig

# Create PEV agent
config = PEVConfig(
    llm_provider="openai",
    model="gpt-4",
    max_iterations=10,                    # Max refinement loops
    verification_strictness="strict",     # strict, medium, lenient
    enable_error_recovery=True,           # Continue on errors
    min_confidence_threshold=0.8          # Stop when confidence > 0.8
)

agent = PEVAgent(config=config)

# Execute task with iterative refinement
result = agent.run(task="Generate Python code with passing tests")

# Access refinement details
print(f"Iterations: {len(result['refinements'])}")
# Output: "Iterations: 3"

print(result["verification"])
# Output: {
#   "passed": True,
#   "confidence": 0.92,
#   "issues_found": ["Minor style issue on line 23"],
#   "issues_fixed": 2
# }

print(result["refinements"])
# Output: [
#   {"iteration": 1, "issue": "Syntax error", "fix": "Added missing colon"},
#   {"iteration": 2, "issue": "Test failure", "fix": "Fixed edge case"},
#   {"iteration": 3, "issue": "Style", "fix": "Added docstring"}
# ]

print(result["final_result"])
# Output: "def fibonacci(n):\n    \"\"\"Calculate fibonacci...\"\"\"\n..."
```

**Verification Strictness:**

| Level | Tolerance | Refinement Triggers | Use Case |
|-------|-----------|---------------------|----------|
| `strict` | Zero errors | All issues | Critical code, production |
| `medium` | Minor warnings OK | Major issues only | Standard development |
| `lenient` | Best effort | Critical issues | Experimental, prototyping |

**Location:** `kaizen.agents.specialized.pev`
**Examples:** `examples/1-single-agent/pev-agent/`
**Guide:** [Planning Agents Guide](../guides/planning-agents-guide.md)

## Meta-Controller Routing API

### Router Pipeline

**Intelligent agent routing via A2A capability matching**

```python
from kaizen.orchestration.pipeline import Pipeline
from kaizen.agents import SimpleQAAgent, CodeGenerationAgent, DataAnalystAgent

# Create specialized agents
qa_agent = SimpleQAAgent(config=QAConfig())
code_agent = CodeGenerationAgent(config=CodeConfig())
data_agent = DataAnalystAgent(config=DataConfig())

# Each agent has A2A capability card
qa_agent.capability = "Question answering and general knowledge"
code_agent.capability = "Code generation and analysis"
data_agent.capability = "Data analysis and visualization"

# Create semantic router (NO hardcoded if/else logic!)
pipeline = Pipeline.router(
    agents=[qa_agent, code_agent, data_agent],
    routing_strategy="semantic",  # Options: semantic, round-robin, random
    error_handling="graceful",     # Options: graceful, fail-fast
    fallback_agent=qa_agent        # Default if no match
)

# Route task to best agent automatically
result = pipeline.run(
    task="Analyze sales data and create visualization",
    input="sales.csv"
)

# A2A automatically selected data_agent (score: 0.9)
print(result["selected_agent"])
# Output: "DataAnalystAgent"

print(result["confidence_score"])
# Output: 0.9
```

**Routing Strategies:**

```python
# 1. Semantic Routing (A2A capability matching)
pipeline = Pipeline.router(
    agents=[agent1, agent2, agent3],
    routing_strategy="semantic"  # Uses Google A2A protocol
)

# 2. Round-Robin (distribute load evenly)
pipeline = Pipeline.router(
    agents=[agent1, agent2, agent3],
    routing_strategy="round-robin"
)

# 3. Random (random selection)
pipeline = Pipeline.router(
    agents=[agent1, agent2, agent3],
    routing_strategy="random"
)
```

**Error Handling:**

```python
from kaizen.orchestration.pipeline import Pipeline

# Graceful error handling (try fallback agent)
pipeline = Pipeline.router(
    agents=[primary_agent, secondary_agent],
    error_handling="graceful",
    fallback_agent=qa_agent,
    max_retries=3
)

# Fail-fast (raise error immediately)
pipeline = Pipeline.router(
    agents=[agent1, agent2],
    error_handling="fail-fast"
)
```

**Location:** `kaizen.orchestration.patterns.meta_controller`
**Examples:** `examples/2-multi-agent/meta-controller/`
**Guide:** [Meta-Controller Routing Guide](../guides/meta-controller-routing-guide.md)

## Configuration Reference

### BaseAgentConfig

```python
from kaizen.core.config import BaseAgentConfig

config = BaseAgentConfig(
    # LLM settings
    llm_provider="openai",  # openai, anthropic, ollama
    model="gpt-4",
    temperature=0.7,
    max_tokens=1000,

    # Provider-specific settings
    provider_config={
        "top_p": 0.9,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "response_format": {"type": "json_object"}  # Structured outputs
    },

    # Performance settings
    timeout=30,
    retry_attempts=3,
    stream=False,

    # Caching settings
    cache_enabled=True,
    cache_ttl=3600,
    cache_key_strategy="content_hash",

    # Monitoring settings
    enable_metrics=True,
    enable_tracing=False,
    log_level="INFO"
)
```

### AutonomousConfig

```python
from kaizen.agents.autonomous.config import AutonomousConfig

config = AutonomousConfig(
    # Base agent settings
    llm_provider="openai",
    model="gpt-4",
    temperature=0.7,

    # Autonomy settings
    max_cycles=15,                      # Max autonomous cycles
    convergence_threshold=0.9,          # Stop when confidence > 0.9
    planning_enabled=True,              # Enable planning phase

    # Lifecycle settings
    enable_hooks=True,                  # Enable hook system
    enable_checkpoints=True,            # Enable checkpoints
    checkpoint_frequency=5,             # Checkpoint every 5 cycles
    enable_interrupts=True,             # Enable interrupt handling
    graceful_shutdown_timeout=5.0,      # Graceful shutdown timeout
    checkpoint_on_interrupt=True,       # Save checkpoint on interrupt

    # Memory settings
    enable_memory=True,
    memory_type="hierarchical",         # hierarchical, buffer, vector
    hot_tier_size=1000,
    warm_tier_size=10000,

    # Budget settings
    max_budget_usd=10.0,
    budget_alert_threshold=0.8
)
```

## Error Codes Reference

### Framework Errors

| Error Code | Description | Resolution |
|------------|-------------|------------|
| `KAIZEN_001` | Framework initialization failed | Check configuration validity |
| `KAIZEN_002` | Invalid configuration provided | Review configuration schema |
| `KAIZEN_003` | Required dependency missing | Install missing dependencies |

### Agent Errors

| Error Code | Description | Resolution |
|------------|-------------|------------|
| `AGENT_001` | Agent creation failed | Check agent configuration |
| `AGENT_002` | Invalid signature provided | Verify signature definition |
| `AGENT_003` | Execution timeout | Increase timeout or optimize |
| `AGENT_004` | Model API error | Check API credentials and limits |
| `AGENT_005` | Convergence failed | Adjust convergence threshold or max_cycles |

### Autonomy System Errors

| Error Code | Description | Resolution |
|------------|-------------|------------|
| `HOOK_001` | Hook registration failed | Check hook handler signature |
| `HOOK_002` | Hook execution timeout | Increase hook timeout |
| `HOOK_003` | Hook execution error | Check hook implementation |
| `CHECKPOINT_001` | Checkpoint save failed | Verify storage backend |
| `CHECKPOINT_002` | Checkpoint load failed | Check checkpoint ID validity |
| `CHECKPOINT_003` | Storage backend unavailable | Verify filesystem/database access |
| `INTERRUPT_001` | Interrupt handler error | Check handler implementation |
| `INTERRUPT_002` | Graceful shutdown timeout | Increase shutdown timeout |
| `MEMORY_001` | Memory backend error | Check database connection |
| `MEMORY_002` | Tier promotion failed | Check tier configuration |

### Execution Errors

| Error Code | Description | Resolution |
|------------|-------------|------------|
| `EXEC_001` | Invalid input format | Check input against signature |
| `EXEC_002` | Workflow build failed | Verify workflow configuration |
| `EXEC_003` | Runtime execution error | Check runtime setup and resources |

## Performance Reference

### Benchmarks

**Framework Initialization:**
- Cold start: ~50ms (improved from 1116ms)
- Warm start: ~10ms

**Agent Creation:**
- Simple agent: <50ms average
- Complex agent with signature: <100ms average
- Autonomous agent with hooks: <200ms average

**Execution Performance:**
- Simple Q&A: <2 seconds (95th percentile)
- Complex reasoning: <10 seconds (95th percentile)
- Multi-agent coordination: <30 seconds (95th percentile)
- Autonomous task (15 cycles): <5 minutes (95th percentile)

**Hooks System:**
- Hook registration: <1ms per hook
- Hook execution overhead: <10ms per event
- High-priority hooks: <5ms overhead

**Checkpoint System:**
- Checkpoint save (filesystem): <50ms
- Checkpoint load (filesystem): <30ms
- Checkpoint save (database): <200ms
- Fork operation: <100ms

**Memory System:**
- Hot tier access: <1ms (target)
- Warm tier access: <10ms (target)
- Cold tier access: <100ms (target)
- Tier promotion: <5ms

### Optimization Guidelines

**Memory Usage:**
- Framework overhead: ~30MB (improved from 50MB)
- Per-agent overhead: ~5MB
- Hook manager: ~2MB
- Checkpoint system: ~1MB
- Model context: Variable based on model

**Throughput:**
- Single agent: >100 queries/minute
- Multi-agent: >20 coordinated tasks/minute
- Autonomous workflows: >5 complex tasks/hour

**Cost Optimization:**
- Use appropriate model for task complexity
- Enable caching for repeated queries (90% cache hit = 10x cost reduction)
- Implement checkpoint frequency tuning
- Use budget interrupt handlers

## Integration Patterns

### Kailash Core SDK Integration

```python
# Standard Core SDK pattern
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "agent", config)
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# Enhanced Kaizen pattern
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature

agent = BaseAgent(config=config, signature=MySignature())
runtime = LocalRuntime()
results, run_id = runtime.execute(agent.to_workflow().build())
```

### DataFlow Integration

```python
from dataflow import DataFlow
from kaizen.memory.backends import DataFlowBackend
from kaizen.agents import SimpleQAAgent

# Setup DataFlow for memory persistence
db = DataFlow(database_url="postgresql://localhost/kaizen")

@db.model
class AgentMemory:
    conversation_id: str
    content: str
    timestamp: str

# Create memory backend
memory_backend = DataFlowBackend(db, model_name="AgentMemory")

# Create agent with persistent memory
agent = SimpleQAAgent(
    config=config,
    memory_backend=memory_backend
)

# Agent automatically persists conversation history
result = agent.ask("What is AI?", session_id="user123")
```

### Nexus Integration

```python
from nexus import Nexus
from kaizen.agents import SimpleQAAgent, CodeGenerationAgent

# Create Nexus platform
nexus = Nexus(
    title="AI Agent Platform",
    enable_api=True,
    enable_cli=True,
    enable_mcp=True
)

# Deploy Kaizen agents
qa_agent = SimpleQAAgent(QAConfig())
code_agent = CodeGenerationAgent(CodeConfig())

nexus.register("qa_agent", qa_agent.to_workflow().build())
nexus.register("code_agent", code_agent.to_workflow().build())

# Available on all channels:
# - API: POST /workflows/qa_agent
# - CLI: nexus run qa_agent
# - MCP: qa_agent tool for AI assistants
```

### Full Stack Integration (All Subsystems)

```python
from kaizen.agents.autonomous import BaseAutonomousAgent, AutonomousConfig
from kaizen.core.autonomy.hooks import HookManager, HookEvent
from kaizen.core.autonomy.state import StateManager, FilesystemStorage
from kaizen.core.autonomy.interrupts.handlers import TimeoutInterruptHandler, BudgetInterruptHandler
from kaizen.memory.backends import DataFlowBackend
from dataflow import DataFlow

# Setup DataFlow for memory
db = DataFlow(database_url="postgresql://localhost/kaizen")

@db.model
class ConversationMemory:
    id: str
    conversation_id: str
    content: str

memory_backend = DataFlowBackend(db, model_name="ConversationMemory")

# Setup hooks
hook_manager = HookManager()
hook_manager.register(
    HookEvent.POST_AGENT_LOOP,
    lambda ctx: HookResult(success=True)
)

# Setup state manager
state_manager = StateManager(
    storage=FilesystemStorage("./checkpoints"),
    checkpoint_frequency=5,
    hook_manager=hook_manager
)

# Setup interrupt handlers
timeout_handler = TimeoutInterruptHandler(timeout_seconds=300.0)
budget_handler = BudgetInterruptHandler(max_budget_usd=10.0)

# Create autonomous agent with all subsystems
config = AutonomousConfig(
    llm_provider="openai",
    model="gpt-4",
    max_cycles=15,
    planning_enabled=True,
    enable_hooks=True,
    enable_checkpoints=True,
    enable_interrupts=True,
    enable_memory=True,
    max_budget_usd=10.0
)

agent = BaseAutonomousAgent(
    config=config,
    signature=TaskSignature(),
    hook_manager=hook_manager,
    state_manager=state_manager,
    memory_backend=memory_backend
)

# Add interrupt handlers
agent.interrupt_manager.add_handler(timeout_handler)
agent.interrupt_manager.add_handler(budget_handler)

# Run autonomous task with full observability
try:
    result = await agent.run_autonomous(
        task="Research and summarize AI ethics papers",
        session_id="research_session_123"
    )
except InterruptedError as e:
    # Gracefully handle interrupts
    checkpoint_id = e.reason.metadata.get("checkpoint_id")
    if checkpoint_id:
        # Resume from checkpoint later
        restored_state = await state_manager.load_checkpoint(checkpoint_id)
```

---

**📚 Complete API Reference**: This comprehensive reference provides all necessary information for developing with the Kaizen Framework, from basic usage to advanced enterprise features with full autonomy support.

**Related Documentation:**
- [Autonomy System Overview](../guides/autonomy-system-overview.md) - High-level overview of autonomy features
- [Hooks System Guide](../guides/hooks-system-guide.md) - Detailed hooks implementation
- [Planning Agents Guide](../guides/planning-agents-guide.md) - Planning agent patterns
- [Meta-Controller Routing Guide](../guides/meta-controller-routing-guide.md) - Intelligent routing
- [Troubleshooting](./troubleshooting.md) - Common issues and solutions
