# LocalKaizenAdapter Developer Guide

## Overview

The `LocalKaizenAdapter` is Kaizen's native autonomous agent implementation that provides Claude Code-like capabilities while working with **any LLM provider**. It implements the Think-Act-Observe-Decide (TAOD) loop with full state management, checkpointing, and integration with Kaizen's existing infrastructure.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    LocalKaizenAdapter                        │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Config    │  │    State    │  │   Infrastructure    │  │
│  │ (Autonomous │  │ (Execution  │  │  (StateManager,     │  │
│  │   Config)   │  │   State)    │  │   HookManager,      │  │
│  └─────────────┘  └─────────────┘  │   InterruptManager) │  │
│                                     └─────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                      TAOD Loop                               │
│  ┌──────┐    ┌─────┐    ┌─────────┐    ┌────────┐          │
│  │THINK │───►│ ACT │───►│ OBSERVE │───►│ DECIDE │──┐       │
│  └──────┘    └─────┘    └─────────┘    └────────┘  │       │
│       ▲                                      │      │       │
│       └──────────────────────────────────────┘      │       │
│                                              (loop) │       │
│                                                     ▼       │
│                                              [Complete]     │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### Basic Usage

```python
from kaizen.runtime.adapters import LocalKaizenAdapter
from kaizen.runtime.adapters.types import AutonomousConfig
from kaizen.runtime.context import ExecutionContext

# Create adapter with default config
adapter = LocalKaizenAdapter()

# Or with custom configuration
config = AutonomousConfig(
    model="gpt-4o",
    max_cycles=100,
    budget_limit_usd=1.0,
)
adapter = LocalKaizenAdapter(config=config)

# Execute a task
context = ExecutionContext(
    task="List all Python files in the current directory",
    session_id="my-session-001",
)
result = await adapter.execute(context)

print(f"Output: {result.output}")
print(f"Status: {result.status}")
print(f"Cycles: {result.cycles_used}")
print(f"Cost: ${result.cost_usd:.4f}")
```

### With Infrastructure Integration

```python
from kaizen.core.autonomy.state.manager import StateManager
from kaizen.core.autonomy.hooks.manager import HookManager
from kaizen.core.autonomy.interrupts.manager import InterruptManager

# Create infrastructure components
state_manager = StateManager(checkpoint_frequency=5)
hook_manager = HookManager()
interrupt_manager = InterruptManager()

# Create adapter with full infrastructure
adapter = LocalKaizenAdapter(
    config=AutonomousConfig(
        model="gpt-4o",
        checkpoint_on_interrupt=True,
    ),
    state_manager=state_manager,
    hook_manager=hook_manager,
    interrupt_manager=interrupt_manager,
)

# Execute with automatic checkpointing and hooks
result = await adapter.execute(context)
```

## Configuration

### AutonomousConfig Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `llm_provider` | str | "openai" | LLM provider to use |
| `model` | str | "gpt-4o" | Model name |
| `temperature` | float | 0.7 | Generation temperature |
| `max_cycles` | int | 50 | Maximum TAOD cycles |
| `budget_limit_usd` | float | None | Cost limit in USD |
| `timeout_seconds` | float | None | Execution timeout |
| `checkpoint_frequency` | int | 10 | Checkpoint every N cycles |
| `checkpoint_on_interrupt` | bool | True | Checkpoint when interrupted |
| `enable_learning` | bool | False | Enable pattern learning |
| `planning_strategy` | PlanningStrategy | REACT | Planning strategy to use |
| `permission_mode` | PermissionMode | CONFIRM_DANGEROUS | Tool permission mode |

### Planning Strategies

```python
from kaizen.runtime.adapters.types import PlanningStrategy

# ReAct: Simple step-by-step reasoning (default)
config = AutonomousConfig(planning_strategy=PlanningStrategy.REACT)

# PEV: Plan-Execute-Verify cycle
config = AutonomousConfig(planning_strategy=PlanningStrategy.PEV)

# Tree-of-Thoughts: Multi-path exploration (experimental)
config = AutonomousConfig(planning_strategy=PlanningStrategy.TREE_OF_THOUGHTS)
```

### Permission Modes

```python
from kaizen.runtime.adapters.types import PermissionMode

# AUTO: Auto-approve safe tools, deny dangerous
config = AutonomousConfig(permission_mode=PermissionMode.AUTO)

# CONFIRM_ALL: Require approval for all tools
config = AutonomousConfig(permission_mode=PermissionMode.CONFIRM_ALL)

# CONFIRM_DANGEROUS: Only confirm dangerous tools (default)
config = AutonomousConfig(permission_mode=PermissionMode.CONFIRM_DANGEROUS)

# DENY_ALL: Deny all tools (read-only mode)
config = AutonomousConfig(permission_mode=PermissionMode.DENY_ALL)
```

## TAOD Loop Phases

### THINK Phase
The agent calls the LLM with the current context to decide the next action:
- Builds system prompt based on strategy
- Includes conversation history
- Formats memory context
- Extracts tool calls from response

### ACT Phase
Executes pending tool calls:
- Checks tool permissions
- Executes tools via registry
- Records results
- Fires tool execution hooks

### OBSERVE Phase
Processes tool results:
- Formats results for conversation
- Updates working memory
- Extracts patterns (if learning enabled)

### DECIDE Phase
Determines whether to continue:
- No tool calls = task complete
- Max cycles reached = stop
- Budget exceeded = stop
- Interrupted = stop

## Streaming

```python
# Stream execution output
async for chunk in adapter.stream(context):
    print(chunk, end="", flush=True)
```

## Interruption

```python
# Interrupt an ongoing execution
success = await adapter.interrupt(
    session_id="my-session-001",
    mode="graceful",  # or "immediate", "rollback"
)
```

## Hooks

The adapter fires lifecycle hooks at key points:

| Hook | When Fired | Data |
|------|------------|------|
| `execution_start` | Execution begins | task, session_id |
| `execution_complete` | Execution ends | task, session_id, cycles, status |
| `execution_error` | Error occurs | task, session_id, error |
| `cycle_start` | Each TAOD cycle | cycle, session_id |
| `tool_start` | Before tool execution | tool_name, tool_args, tool_id |
| `tool_complete` | After tool execution | tool_name, tool_id, success |
| `tool_error` | Tool execution fails | tool_name, tool_id, error |
| `interrupt` | Interrupt requested | session_id, cycle, reason |
| `checkpoint_created` | Checkpoint saved | checkpoint_id, session_id, cycle |

## Cost Tracking

The adapter tracks token usage and costs:

```python
result = await adapter.execute(context)
print(f"Tokens used: {result.tokens_used}")
print(f"Cost: ${result.cost_usd:.4f}")
```

Supported models with pricing:
- OpenAI: gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-4, gpt-3.5-turbo
- Anthropic: claude-3-opus, claude-3-sonnet, claude-3-haiku, claude-3-5-sonnet

## Working Memory

The adapter maintains working memory during execution:

```python
# Access during execution via state
state.working_memory["file_list"] = ["a.txt", "b.txt"]
state.working_memory["current_focus"] = "analyzing imports"
```

## Pattern Learning

When `enable_learning=True`, the adapter can learn patterns:

```python
config = AutonomousConfig(enable_learning=True)
adapter = LocalKaizenAdapter(config=config)

# After execution, patterns are stored in state
# state.learned_patterns contains learned patterns
```

## Best Practices

1. **Set Appropriate Limits**: Always configure `max_cycles` and `budget_limit_usd` to prevent runaway execution.

2. **Use Checkpointing**: Enable `checkpoint_on_interrupt` and set reasonable `checkpoint_frequency` for long-running tasks.

3. **Choose the Right Strategy**: Use REACT for simple tasks, PEV for complex multi-step tasks.

4. **Permission Modes**: Start with `CONFIRM_DANGEROUS` and adjust based on use case.

5. **Infrastructure Integration**: Use StateManager, HookManager, and InterruptManager for production deployments.

## API Reference

### LocalKaizenAdapter

```python
class LocalKaizenAdapter(BaseRuntimeAdapter):
    def __init__(
        self,
        config: Optional[AutonomousConfig] = None,
        state_manager: Optional[Any] = None,
        hook_manager: Optional[Any] = None,
        interrupt_manager: Optional[Any] = None,
        tool_registry: Optional[Any] = None,
        llm_provider: Optional[Any] = None,
    ): ...

    async def execute(
        self,
        context: ExecutionContext,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ExecutionResult: ...

    async def stream(
        self,
        context: ExecutionContext,
    ) -> AsyncIterator[str]: ...

    async def interrupt(
        self,
        session_id: str,
        mode: str = "graceful",
    ) -> bool: ...

    @property
    def capabilities(self) -> RuntimeCapabilities: ...
```

### ExecutionState

```python
@dataclass
class ExecutionState:
    task: str
    session_id: str
    current_cycle: int
    phase: AutonomousPhase
    messages: List[Dict[str, Any]]
    plan: List[str]
    plan_index: int
    pending_tool_calls: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]
    working_memory: Dict[str, Any]
    learned_patterns: List[str]
    tokens_used: int
    cost_usd: float
    status: str  # running, completed, interrupted, error
    result: Optional[str]
    error: Optional[str]
```
