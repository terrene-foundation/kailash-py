# Autonomy System Overview

**Version**: 1.0.0
**Status**: Production Ready
**Last Updated**: 2025-11-03

---

## Executive Summary

The Kaizen Autonomy System provides production-ready infrastructure for building long-running AI agents that execute complex tasks over multiple cycles without human intervention. The system implements proven patterns from Claude Code and Codex, validated through 100+ tests and real-world deployments.

**Core Capabilities:**
- **Lifecycle Management**: Hooks system for zero-code-change observability
- **State Persistence**: Checkpoint/resume/fork capabilities
- **Interrupt Handling**: Graceful shutdown coordination
- **Memory System**: 3-tier hierarchical storage (Hot/Warm/Cold)
- **Tool Integration**: 12 builtin tools with danger-level approval workflows
- **Multi-Agent Coordination**: Google A2A protocol integration

---

## Table of Contents

1. [What is Autonomy?](#what-is-autonomy)
2. [Architecture Overview](#architecture-overview)
3. [Subsystems](#subsystems)
4. [Quick Start](#quick-start)
5. [Production Deployment](#production-deployment)
6. [When to Use Autonomy](#when-to-use-autonomy)
7. [Next Steps](#next-steps)

---

## What is Autonomy?

**Autonomous agents** execute complex tasks over multiple cycles using the proven `while(tool_calls_exist)` pattern:

```python
while tool_calls_exist:
    gather_context()  # Read files, search code
    take_action()     # Edit files, run commands
    verify()          # Check results, run tests
    iterate()         # Update plan, continue
```

### Key Characteristics

| Feature | Single-Shot Agent | Autonomous Agent |
|---------|------------------|------------------|
| Execution | One cycle | Multi-cycle (5-100+) |
| Convergence | After first response | Objective via tool_calls |
| Use Case | Q&A, classification | Coding, research, data analysis |
| Planning | None | TODO-based structured plans |
| Checkpoints | No | Yes (JSONL format) |
| Duration | Seconds | Minutes to hours |
| Observability | Basic | Hooks, metrics, tracing |

### Real-World Example

```python
# USER REQUEST: "Fix authentication timeout bug and add tests"

# CYCLE 1 (2s): Gather context
tool_calls = [read_file("auth/user.py"), grep_search("timeout")]
# Result: Found timeout logic in auth/user.py:47

# CYCLE 2 (3s): Analyze code
tool_calls = [read_file("auth/session.py")]
# Result: Session expires after 30min, should be 60min

# CYCLE 3 (2s): Fix bug
tool_calls = [edit_file("auth/session.py", old="30", new="60")]
# Result: File updated successfully

# CYCLE 4 (5s): Add tests
tool_calls = [write_file("tests/test_auth.py", content="...")]
# Result: Test file created

# CYCLE 5 (8s): Run tests
tool_calls = [bash_command("pytest tests/test_auth.py")]
# Result: 3 tests PASSED

# CYCLE 6 (1s): Verify completion
tool_calls = []  # Empty = converged
# Result: Bug fixed, tests added and passing

# TOTAL: 6 cycles, 21 seconds, task complete
```

---

## Architecture Overview

The autonomy system consists of 6 subsystems working together:

```
┌─────────────────────────────────────────────────────────────────┐
│                    AUTONOMY SYSTEM                              │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   Lifecycle  │  │    State     │  │  Interrupt   │         │
│  │   (Hooks)    │  │ Persistence  │  │  Mechanism   │         │
│  │              │  │              │  │              │         │
│  │ PRE/POST     │  │ Save/Load/   │  │ Graceful     │         │
│  │ Events       │  │ Fork         │  │ Shutdown     │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   Memory     │  │    Tools     │  │ Multi-Agent  │         │
│  │   System     │  │   Calling    │  │ Coordination │         │
│  │              │  │              │  │              │         │
│  │ Hot/Warm/    │  │ 12 Builtin + │  │ Google A2A   │         │
│  │ Cold Tiers   │  │ MCP Servers  │  │ Protocol     │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│                                                                 │
│         ▲                    ▲                    ▲             │
│         │                    │                    │             │
│         └────────────────────┴────────────────────┘             │
│                      BaseAgent Core                             │
└─────────────────────────────────────────────────────────────────┘
```

### Execution Flow

```
1. START: User submits task to autonomous agent
   ↓
2. HOOKS: PRE_AGENT_LOOP triggered
   → Audit log: "Agent loop started at 2025-11-03T10:00:00"
   → Metrics: Start timer
   ↓
3. CHECKPOINT: Load latest state (if resuming)
   → StateManager.resume_from_latest("agent_id")
   ↓
4. CYCLE 1: Execute first iteration
   ├─ HOOKS: PRE_CYCLE triggered
   ├─ LLM: Generate response with tool_calls
   ├─ TOOLS: Execute tools (if any)
   ├─ MEMORY: Store turn in appropriate tier
   ├─ HOOKS: POST_CYCLE triggered
   └─ CONVERGENCE: Check if done (tool_calls == [])
   ↓
5. CHECKPOINT: Save state every N cycles
   → StateManager.save_checkpoint(agent_state)
   ↓
6. INTERRUPT CHECK: User pressed Ctrl+C?
   → InterruptManager.check_interrupt()
   → If yes: Graceful shutdown, save final checkpoint
   ↓
7. CYCLE 2...N: Repeat steps 4-6 until:
   - Converged (tool_calls == [])
   - Max cycles reached
   - Interrupted by user/system/budget
   ↓
8. HOOKS: POST_AGENT_LOOP triggered
   → Audit log: "Agent loop completed, 6 cycles, 21s"
   → Metrics: Record duration, cost, cycles
   ↓
9. RETURN: Final result to user
```

---

## Subsystems

### 1. Lifecycle Management (Hooks System)

**Purpose**: Zero-code-change observability and extension points for agent lifecycle events.

**Key Events**:
- `PRE_AGENT_LOOP` / `POST_AGENT_LOOP` - Full execution lifecycle
- `PRE_CYCLE` / `POST_CYCLE` - Individual iteration boundaries
- `PRE_TOOL_CALL` / `POST_TOOL_CALL` - Tool execution tracking
- `PRE_CHECKPOINT_SAVE` / `POST_CHECKPOINT_SAVE` - State persistence events

**Example**:
```python
from kaizen.core.autonomy.hooks import HookManager, HookEvent

async def audit_hook(context):
    print(f"Agent {context.agent_id} at cycle {context.metadata['cycle']}")
    return HookResult(success=True)

hook_manager = HookManager()
hook_manager.register(HookEvent.POST_CYCLE, audit_hook)

agent = BaseAgent(config, signature, hook_manager=hook_manager)
```

**Documentation**: [Hooks System Guide](hooks-system-guide.md)

### 2. State Persistence (Checkpoint System)

**Purpose**: Save/load/fork agent state for recovery and branching.

**Key Operations**:
- `save_checkpoint()` - Persist current state
- `load_checkpoint(id)` - Restore from checkpoint
- `resume_from_latest()` - Continue from last checkpoint
- `fork_from_checkpoint(id)` - Create independent branch

**Example**:
```python
from kaizen.core.autonomy.state import StateManager, FilesystemStorage

storage = FilesystemStorage(base_dir="./checkpoints")
state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=10,  # Every 10 cycles
    retention_count=100       # Keep last 100
)

# Auto-checkpointing during execution
checkpoint_id = await state_manager.save_checkpoint(agent_state)

# Resume from latest
latest_state = await state_manager.resume_from_latest("agent_id")
```

**Documentation**: [State Persistence Guide](state-persistence-guide.md)

### 3. Interrupt Mechanism (Graceful Shutdown)

**Purpose**: Coordinate graceful shutdown across agents, saving state before exit.

**Interrupt Sources**:
- **USER**: Ctrl+C, manual stop
- **SYSTEM**: Timeout, budget limit, resource exhaustion
- **PROGRAMMATIC**: API call, hook trigger

**Shutdown Modes**:
- **GRACEFUL**: Finish current cycle, save checkpoint (5s timeout)
- **IMMEDIATE**: Stop now, may lose state

**Example**:
```python
from kaizen.core.autonomy.interrupts.handlers import TimeoutInterruptHandler

config = AutonomousConfig(
    enable_interrupts=True,
    graceful_shutdown_timeout=5.0,
    checkpoint_on_interrupt=True
)

agent = BaseAutonomousAgent(config, signature)
agent.interrupt_manager.add_handler(TimeoutInterruptHandler(timeout_seconds=30))

try:
    result = await agent.run_autonomous(task)
except InterruptedError as e:
    checkpoint_id = e.reason.metadata.get("checkpoint_id")
    print(f"Interrupted: {e.reason.message}, checkpoint: {checkpoint_id}")
```

**Documentation**: [Interrupt Mechanism Guide](interrupt-mechanism-guide.md)

### 4. Memory System (3-Tier Storage)

**Purpose**: Hierarchical storage with automatic tier promotion/demotion based on access patterns.

**Tiers**:
- **Hot** (< 1ms): In-memory cache with LRU/LFU/FIFO eviction
- **Warm** (< 10ms): Local database (SQLite)
- **Cold** (< 100ms): Remote database (PostgreSQL)

**Example**:
```python
from kaizen.memory.tiers import HotMemoryTier
from kaizen.memory.backends import DataFlowBackend
from dataflow import DataFlow

# Hot tier (in-memory)
hot_tier = HotMemoryTier(max_size=1000, eviction_policy="lru")
await hot_tier.put("key", value, ttl=300)
data = await hot_tier.get("key")  # < 1ms

# Cold tier (DataFlow backend)
db = DataFlow(database_url="postgresql://...")

@db.model
class ConversationMessage:
    id: str
    conversation_id: str
    content: str

backend = DataFlowBackend(db, model_name="ConversationMessage")
backend.save_turn("session_123", {"user": "Hello", "agent": "Hi"})
turns = backend.load_turns("session_123", limit=10)  # < 100ms
```

**Documentation**: Memory System Guide (see CLAUDE.md)

### 5. Tool Integration (MCP-Based)

**Purpose**: Autonomous tool calling with danger-level approval workflows.

**12 Builtin Tools**:
- **File (5)**: read_file, write_file, delete_file, list_directory, file_exists
- **HTTP (4)**: http_get, http_post, http_put, http_delete
- **Bash (1)**: bash_command
- **Web (2)**: fetch_url, extract_links

**Danger Levels**:
- **SAFE**: Auto-approve (read_file, http_get)
- **MODERATE**: Prompt user (write_file, http_post)
- **DANGEROUS**: Require confirmation (delete_file, bash_command)
- **CRITICAL**: Multi-factor approval (system commands)

**Example**:
```python
from kaizen.core.base_agent import BaseAgent

# Tools auto-configured via MCP
agent = BaseAgent(config, signature, tools="all")

# Discover tools by category
file_tools = await agent.discover_tools(category="file")

# Execute single tool
result = await agent.execute_tool("read_file", {"path": "data.txt"})

# Chain multiple tools
results = await agent.execute_tool_chain([
    {"tool_name": "read_file", "params": {"path": "input.txt"}},
    {"tool_name": "write_file", "params": {"path": "output.txt", "content": "..."}}
])
```

**Documentation**: See CLAUDE.md section "Tool Calling"

### 6. Multi-Agent Coordination (Google A2A)

**Purpose**: Coordinate multiple autonomous agents using capability-based semantic matching.

**Patterns**:
- **SupervisorWorker**: Supervisor routes tasks to best worker (semantic matching)
- **Consensus**: Iterative voting until agreement
- **Debate**: Back-and-forth argumentation
- **Sequential**: Pipeline execution
- **Handoff**: Task passing

**Example**:
```python
from kaizen.agents.coordination.supervisor_worker import SupervisorWorkerPattern

# Automatic A2A capability-based routing
pattern = SupervisorWorkerPattern(supervisor, workers, coordinator, shared_pool)

# Semantic task routing (no hardcoded logic!)
best_worker = pattern.supervisor.select_worker_for_task(
    task="Analyze sales data and create visualization",
    available_workers=[code_expert, data_expert, writing_expert],
    return_score=True
)
# Returns: {"worker": <DataAnalystAgent>, "score": 0.9}
```

**Documentation**: [Multi-Agent Coordination Guide](multi-agent-coordination.md)

---

## Quick Start

### 1. Basic Autonomous Agent

```python
from kaizen.agents.autonomous import BaseAutonomousAgent, AutonomousConfig
from kaizen.signatures import Signature, InputField, OutputField

# Define signature
class ResearchSignature(Signature):
    task: str = InputField(description="Research task")
    observation: str = InputField(description="Last observation", default="")

    findings: str = OutputField(description="Research findings")
    next_action: str = OutputField(description="Next action")
    tool_calls: list = OutputField(description="Tool calls", default=[])

# Configure agent
config = AutonomousConfig(
    llm_provider="openai",
    model="gpt-4",
    max_cycles=15,
    planning_enabled=True,
    checkpoint_frequency=5
)

# Create agent (tools auto-configured via MCP)
agent = BaseAutonomousAgent(config=config, signature=ResearchSignature())

# Execute autonomously
result = await agent.execute_autonomously(
    "Research Python async programming patterns and create summary"
)

print(f"✅ Completed in {result['cycles_used']} cycles")
print(f"Findings: {result.get('findings', 'N/A')}")
```

### 2. Agent with Hooks + Checkpoints + Interrupts

```python
from kaizen.agents.autonomous import BaseAutonomousAgent, AutonomousConfig
from kaizen.core.autonomy.hooks import HookManager, HookEvent
from kaizen.core.autonomy.state import StateManager, FilesystemStorage
from kaizen.core.autonomy.interrupts.handlers import TimeoutInterruptHandler

# Setup hooks
async def audit_hook(context):
    print(f"Cycle {context.metadata['cycle']}: {context.agent_id}")
    return HookResult(success=True)

hook_manager = HookManager()
hook_manager.register(HookEvent.POST_CYCLE, audit_hook)

# Setup checkpointing
storage = FilesystemStorage(base_dir="./checkpoints")
state_manager = StateManager(storage, checkpoint_frequency=10)

# Configure agent with interrupts
config = AutonomousConfig(
    llm_provider="openai",
    model="gpt-4",
    max_cycles=50,
    enable_interrupts=True,
    graceful_shutdown_timeout=5.0,
    checkpoint_on_interrupt=True
)

# Create agent
agent = BaseAutonomousAgent(
    config=config,
    signature=ResearchSignature(),
    hook_manager=hook_manager,
    state_manager=state_manager
)

# Add timeout handler
agent.interrupt_manager.add_handler(TimeoutInterruptHandler(timeout_seconds=300))

# Execute with full autonomy stack
try:
    result = await agent.execute_autonomously("Complex research task")
except InterruptedError as e:
    print(f"Interrupted: {e.reason.message}")
    checkpoint_id = e.reason.metadata.get("checkpoint_id")

    # Resume from checkpoint later
    latest_state = await state_manager.resume_from_latest(agent.agent_id)
```

### 3. Multi-Agent Autonomous Coordination

```python
from kaizen.agents.autonomous import ClaudeCodeAgent, ClaudeCodeConfig
from kaizen.agents.coordination.supervisor_worker import SupervisorWorkerPattern

# Create specialized workers
code_agent = ClaudeCodeAgent(ClaudeCodeConfig(model="gpt-4"))
data_agent = BaseAutonomousAgent(config=data_config, signature=data_sig)
research_agent = BaseAutonomousAgent(config=research_config, signature=research_sig)

# Create coordination pattern
pattern = SupervisorWorkerPattern(
    supervisor=supervisor_agent,
    workers=[code_agent, data_agent, research_agent],
    coordinator=coordinator_agent,
    shared_pool=shared_memory_pool
)

# Execute coordinated task
result = await pattern.execute_task(
    "Analyze codebase, generate documentation, and create deployment guide"
)

# Supervisor automatically routes:
# - Code analysis → code_agent (7 cycles)
# - Documentation → research_agent (5 cycles)
# - Deployment guide → data_agent (4 cycles)
# Total: 16 cycles across 3 agents
```

---

## Production Deployment

### Security Hardening

```python
from kaizen.core.autonomy.hooks.security import (
    AuthorizedHookManager,
    IsolatedHookManager,
    ResourceLimits,
    HookPrincipal,
    HookPermission,
)

# RBAC authorization
admin_principal = HookPrincipal(
    identity="admin@company.com",
    permissions={HookPermission.REGISTER_HOOK, HookPermission.TRIGGER_HOOKS}
)

hook_manager = AuthorizedHookManager()
await hook_manager.register(
    event=HookEvent.POST_AGENT_LOOP,
    handler=my_hook,
    principal=admin_principal  # REQUIRED
)

# Process isolation with resource limits
limits = ResourceLimits(max_memory_mb=100, max_cpu_seconds=5)
isolated_manager = IsolatedHookManager(limits=limits, enable_isolation=True)

# Additional security features:
# - Ed25519 signature verification for filesystem hooks
# - API key authentication + IP whitelisting for metrics
# - Auto-redact API keys, passwords, PII from logs
# - Rate limiting to prevent DoS via hook registration
# - Input validation to block code injection, XSS, path traversal
```

**Compliance**: PCI DSS 4.0, HIPAA § 164.312, GDPR Article 32, SOC 2

**Documentation**: [Security Guide](../SECURITY_GUIDE.md)

### Monitoring and Observability

```python
from kaizen.core.autonomy.hooks import HookManager, HookEvent

# Prometheus metrics
async def prometheus_metrics_hook(context):
    metrics.record("agent_cycle_duration", context.duration_ms)
    metrics.record("agent_cost", context.metadata.get("cost_usd", 0))
    metrics.inc("agent_cycles_total")
    return HookResult(success=True)

# Distributed tracing
async def tracing_hook(context):
    span = tracer.start_span(
        name=f"{context.agent_id}_cycle_{context.metadata['cycle']}",
        parent=context.trace_id
    )
    span.set_tag("agent_id", context.agent_id)
    span.set_tag("cycle", context.metadata['cycle'])
    span.finish()
    return HookResult(success=True)

# Audit trail
async def audit_hook(context):
    audit_log.info({
        "timestamp": context.timestamp,
        "agent_id": context.agent_id,
        "event": context.event_type,
        "cycle": context.metadata.get('cycle'),
        "cost": context.metadata.get('cost_usd'),
        "user": context.metadata.get('user_id')
    })
    return HookResult(success=True)

hook_manager = HookManager()
hook_manager.register(HookEvent.POST_CYCLE, prometheus_metrics_hook)
hook_manager.register(HookEvent.POST_CYCLE, tracing_hook)
hook_manager.register(HookEvent.POST_AGENT_LOOP, audit_hook)
```

**Examples**: `examples/autonomy/hooks/` (audit_trail, distributed_tracing, prometheus_metrics)

### Cost Control

```python
from kaizen.core.autonomy.interrupts.handlers import BudgetInterruptHandler

# Budget-based interrupts
config = AutonomousConfig(
    llm_provider="openai",
    model="gpt-4",
    max_cycles=100,
    enable_interrupts=True
)

agent = BaseAutonomousAgent(config, signature)

# Add budget limit (stop at $1.00)
budget_handler = BudgetInterruptHandler(
    max_budget_usd=1.0,
    track_by="session"  # or "agent", "user"
)
agent.interrupt_manager.add_handler(budget_handler)

# Agent will gracefully stop when budget exceeded
try:
    result = await agent.execute_autonomously(task)
except InterruptedError as e:
    if e.reason.interrupt_type == InterruptType.SYSTEM:
        print(f"Budget exceeded: ${e.reason.metadata['budget_spent_usd']}")
```

---

## When to Use Autonomy

### Use Autonomous Execution When:

✅ **Feedback Loops Required**
- Agent needs to observe results and adjust strategy
- Example: ReAct (Reason → Act → Observe → Repeat)

✅ **Iterative Refinement**
- Agent improves output through multiple attempts
- Example: CodeGeneration (Generate → Test → Fix → Repeat)

✅ **Tool Interaction**
- Agent calls external tools and processes results
- Example: RAGResearch (Query → Fetch → Analyze → Query Again)

✅ **No Clear Termination Point**
- Agent decides when task is complete (convergence detection)
- Example: Research (explore until comprehensive)

✅ **Multi-Step Reasoning with Branching**
- Agent explores different paths dynamically
- Example: SelfReflection (Think → Critique → Revise → Repeat)

### Use Single-Shot Execution When:

✅ **Deterministic Output**
- Agent produces single, final answer
- Example: SimpleQA (Question → Answer)

✅ **Clear Termination**
- Task completes in one pass
- Example: VisionAgent (Image → Description)

✅ **No Tool Interaction**
- Agent only processes inputs to outputs
- Example: ChainOfThought (structured reasoning, one pass)

### Decision Matrix

| Requirement | Use Autonomous | Use Single-Shot |
|-------------|---------------|-----------------|
| Tool calling with iteration | ✅ Yes | ❌ No |
| Generate → Test → Fix cycles | ✅ Yes | ❌ No |
| Research with refinement | ✅ Yes | ❌ No |
| Simple Q&A | ❌ No | ✅ Yes |
| Image/Audio processing | ❌ No | ✅ Yes |
| One-time classification | ❌ No | ✅ Yes |

**Documentation**: [Autonomous Agent Decision Matrix](autonomous-agent-decision-matrix.md)

---

## Next Steps

### Detailed Guides

1. **[Hooks System Guide](hooks-system-guide.md)** - Event-driven observability (6,000+ words)
2. **[State Persistence Guide](state-persistence-guide.md)** - Checkpoint/resume/fork (5,000+ words)
3. **[Interrupt Mechanism Guide](interrupt-mechanism-guide.md)** - Graceful shutdown (4,000+ words)
4. **[Autonomous Patterns Guide](autonomous-patterns.md)** - Complete autonomous agent guide (1,142 lines)

### Architecture Guides

5. **[Autonomous Implementation Patterns](autonomous-implementation-patterns.md)** - Production-ready patterns (808 lines)
6. **[Autonomous Agent Decision Matrix](autonomous-agent-decision-matrix.md)** - When to use autonomy (493 lines)

### Examples

7. **[Autonomy Examples](../../examples/autonomy/)** - Working implementations
   - `lifecycle/` - Checkpoints, interrupts, state
   - `hooks/` - Audit trail, distributed tracing, Prometheus
   - `memory/` - 3-tier storage examples
   - `tools/` - Tool calling patterns
   - `01_base_autonomous_agent_demo.py` - BaseAutonomousAgent with 3 demos
   - `02_claude_code_agent_demo.py` - ClaudeCodeAgent with 4 demos
   - `03_codex_agent_demo.py` - CodexAgent with 5 demos

### API Reference

8. **[API Reference](../reference/api-reference.md)** - Complete API documentation
9. **[Configuration Guide](../reference/configuration.md)** - All config options
10. **[Troubleshooting](../reference/troubleshooting.md)** - Common issues

---

## Summary

The Kaizen Autonomy System provides enterprise-grade infrastructure for long-running AI agents:

**6 Core Subsystems:**
1. **Lifecycle Management (Hooks)** - Zero-code-change observability
2. **State Persistence (Checkpoints)** - Save/load/fork capabilities
3. **Interrupt Mechanism** - Graceful shutdown coordination
4. **Memory System** - 3-tier hierarchical storage
5. **Tool Integration** - 12 builtin tools via MCP
6. **Multi-Agent Coordination** - Google A2A protocol

**Production Ready:**
- ✅ 100+ tests passing (unit, integration, E2E)
- ✅ Security hardening (RBAC, isolation, redaction)
- ✅ Compliance (PCI DSS, HIPAA, GDPR, SOC 2)
- ✅ Monitoring (Prometheus, distributed tracing, audit logs)
- ✅ Cost control (budget limits, auto-interrupts)

**Battle-Tested Patterns:**
- ✅ Claude Code: `while(tool_calls_exist)` pattern
- ✅ Codex: Container-based PR generation
- ✅ Objective convergence detection (ADR-013)
- ✅ Real infrastructure testing (NO MOCKING)

---

**Framework**: Kaizen AI Framework built on Kailash Core SDK
**License**: MIT
**Repository**: https://github.com/kailash-sdk/kaizen
**Documentation**: https://docs.kailash.ai/kaizen/autonomy
