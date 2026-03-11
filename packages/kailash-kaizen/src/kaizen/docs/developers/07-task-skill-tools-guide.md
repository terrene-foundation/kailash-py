# Task/Skill Tools Guide (TODO-203)

This guide covers the Task and Skill tools that enable multi-agent coordination and knowledge injection for autonomous agent execution.

## Overview

The Task/Skill Tools provide two core capabilities:

1. **TaskTool**: Spawns specialized subagents dynamically, similar to Claude Code's Task tool
2. **SkillTool**: Invokes registered skills to inject domain-specific knowledge

These tools are designed for integration with the Specialist System (ADR-013) and enable Enterprise-App patterns including progress visualization, cost attribution, and trust chain propagation.

## TaskTool

TaskTool enables multi-agent coordination by spawning subagents that execute autonomously and return results.

### Basic Usage

```python
from kaizen.tools.native import TaskTool, KaizenToolRegistry
from kaizen.runtime.adapters import LocalKaizenAdapter
from kaizen.core import KaizenOptions, SpecialistDefinition

# Define specialists
specialists = {
    "code-reviewer": SpecialistDefinition(
        description="Code review specialist",
        system_prompt="You are an expert code reviewer.",
        available_tools=["Read", "Glob", "Grep"],
    ),
}

# Create adapter with specialists
options = KaizenOptions(specialists=specialists)
adapter = LocalKaizenAdapter(kaizen_options=options)

# Create TaskTool with adapter
task_tool = TaskTool(
    adapter=adapter,
    parent_agent_id="orchestrator-001",
    trust_chain_id="chain-abc123",
)

# Execute a subagent task
result = await task_tool.execute(
    subagent_type="code-reviewer",
    prompt="Review the authentication module for security issues",
    description="Review auth module",
)

print(result.output.output)  # Subagent's response
print(result.output.tokens_used)  # Token usage
print(result.output.cost_usd)  # Cost in USD
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `subagent_type` | str | Yes | Name of specialist to spawn |
| `prompt` | str | Yes | Task description for subagent |
| `description` | str | No | Short (3-5 word) description for progress display |
| `model` | str | No | Model override (default: specialist's model) |
| `max_turns` | int | No | Maximum execution turns/cycles |
| `run_in_background` | bool | No | Run async and return output file path |
| `resume` | str | No | Subagent ID to resume from checkpoint |

### Background Execution

For long-running tasks, use background execution:

```python
result = await task_tool.execute(
    subagent_type="code-reviewer",
    prompt="Review all Python files in src/",
    run_in_background=True,
)

# Result contains output file path
output_file = result.metadata["output_file"]
print(f"Check progress at: {output_file}")

# Check status later
status = await task_tool.get_background_status(result.metadata["subagent_id"])
```

### SubagentResult

The TaskTool returns a `SubagentResult` with these fields:

```python
@dataclass
class SubagentResult:
    subagent_id: str          # Unique identifier
    output: str               # Subagent's response
    status: str               # completed, error, interrupted, timeout, running
    tokens_used: int          # Token consumption
    cost_usd: float          # Cost in USD
    cycles_used: int         # Execution cycles
    duration_ms: int         # Execution time
    specialist_name: str     # Specialist type used
    model_used: str          # Model used
    parent_agent_id: str     # Parent agent ID
    trust_chain_id: str      # Trust chain for delegation
```

## SkillTool

SkillTool enables knowledge injection by loading skill content dynamically from the registry.

### Basic Usage

```python
from kaizen.tools.native import SkillTool
from kaizen.core import KaizenOptions, SkillDefinition

# Define skills
skills = {
    "python-patterns": SkillDefinition(
        name="python-patterns",
        description="Python design patterns",
        location="/skills/python-patterns",
        source="project",
    ),
}

# Create adapter with skills
options = KaizenOptions(skills=skills)
adapter = LocalKaizenAdapter(kaizen_options=options)

# Create SkillTool with adapter
skill_tool = SkillTool(
    adapter=adapter,
    agent_id="agent-001",
)

# Invoke a skill
result = await skill_tool.execute(skill_name="python-patterns")

print(result.output.content)  # Skill content
print(result.output.additional_files)  # Additional .md files
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `skill_name` | str | Yes | Name of skill to invoke |
| `load_additional_files` | bool | No | Load additional .md files (default: True) |

### Progressive Disclosure

SkillTool supports progressive disclosure - metadata is available without loading content:

```python
# Get skill metadata without loading content
info = skill_tool.get_skill_info("python-patterns")
print(info["name"])        # python-patterns
print(info["description"]) # Python design patterns
print(info["is_loaded"])   # False

# Load content on execute
result = await skill_tool.execute(skill_name="python-patterns")
# Now content is loaded
```

### SkillResult

The SkillTool returns a `SkillResult` with these fields:

```python
@dataclass
class SkillResult:
    skill_name: str                    # Skill identifier
    content: str                       # Main skill content
    success: bool                      # Whether loading succeeded
    description: str                   # Skill description
    location: str                      # Source location
    source: str                        # user/project/local
    additional_files: Dict[str, str]   # Additional .md files
```

## Event Emission

Both tools emit events for Enterprise-App integration, enabling progress visualization, cost tracking, and audit trails.

### TaskTool Events

```python
from kaizen.execution.events import (
    SubagentSpawnEvent,
    SubagentCompleteEvent,
    CostUpdateEvent,
)

events = []

async def capture_event(event):
    events.append(event)

task_tool = TaskTool(
    adapter=adapter,
    on_event=capture_event,
    parent_agent_id="parent-001",
    trust_chain_id="chain-abc",
)

await task_tool.execute(
    subagent_type="code-reviewer",
    prompt="Review the code",
)

# Events emitted:
# 1. SubagentSpawnEvent - when subagent starts
# 2. SubagentCompleteEvent - when subagent finishes
# 3. CostUpdateEvent - with token/cost metrics
```

#### SubagentSpawnEvent

Critical event for TaskGraph visualization:

```python
@dataclass
class SubagentSpawnEvent:
    session_id: str
    subagent_id: str
    subagent_name: str
    task: str
    parent_agent_id: str      # For parent-child relationships
    trust_chain_id: str       # For trust propagation
    capabilities: List[str]   # Available tools
    model: str
    max_turns: int
    run_in_background: bool
```

### SkillTool Events

```python
from kaizen.execution.events import (
    SkillInvokeEvent,
    SkillCompleteEvent,
)

skill_tool = SkillTool(
    adapter=adapter,
    on_event=capture_event,
    agent_id="agent-001",
)

await skill_tool.execute(skill_name="python-patterns")

# Events emitted:
# 1. SkillInvokeEvent - when skill invocation starts
# 2. SkillCompleteEvent - when skill loading completes
```

## Trust Chain Propagation

TaskTool propagates trust chains from parent to child agents, enabling:

- Hierarchical permission inheritance
- Audit trail for delegated actions
- Cost attribution to root agent

```python
# Parent agent creates TaskTool with trust chain
task_tool = TaskTool(
    adapter=adapter,
    parent_agent_id="orchestrator-001",
    trust_chain_id="chain-root-abc",
)

# Subagent inherits trust chain
result = await task_tool.execute(
    subagent_type="code-reviewer",
    prompt="Review the code",
)

# Result includes trust chain info
print(result.output.parent_agent_id)   # orchestrator-001
print(result.output.trust_chain_id)    # chain-root-abc
```

## Registry Integration

Both tools integrate with KaizenToolRegistry:

```python
from kaizen.tools.native import KaizenToolRegistry, TaskTool, SkillTool

registry = KaizenToolRegistry()

# Register agent tools
registry.register_defaults(categories=["agent"])
# Registers: TaskTool, SkillTool

# Or register with custom configuration
registry.register(TaskTool(adapter=adapter))
registry.register(SkillTool(adapter=adapter))

# Execute through registry
result = await registry.execute("task", {
    "subagent_type": "code-reviewer",
    "prompt": "Review the code",
})
```

## Danger Levels

- **TaskTool**: `DangerLevel.MEDIUM` - Creates new agent execution
- **SkillTool**: `DangerLevel.SAFE` - Read-only knowledge injection

## Error Handling

Both tools wrap errors in their result types rather than raising exceptions:

```python
# TaskTool error handling
result = await task_tool.execute(
    subagent_type="unknown-specialist",
    prompt="Do something",
)

if not result.success:
    print(f"Tool error: {result.error}")
else:
    subagent_result = result.output
    if subagent_result.status == "error":
        print(f"Subagent error: {subagent_result.error_message}")

# SkillTool error handling
result = await skill_tool.execute(skill_name="unknown-skill")

if not result.success:
    print(f"Error: {result.error}")
```

## Best Practices

1. **Always provide trust chain IDs** for audit trails and permission inheritance
2. **Use background execution** for tasks expected to take more than a few seconds
3. **Handle both tool and subagent errors** - they're separate failure modes
4. **Register event callbacks** for progress monitoring and cost tracking
5. **Use progressive disclosure** with SkillTool to avoid loading unnecessary content
