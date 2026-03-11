# Autonomous Agent Patterns - Complete Guide

**Version**: 0.1.0
**Status**: Production Ready
**Test Coverage**: 100/100 tests passing
**Created**: 2025-10-22

---

## Overview

This guide covers the autonomous agent patterns implemented in Kaizen Framework, based on proven architectures from Claude Code and Codex (OpenAI). These patterns enable truly autonomous AI agents capable of multi-hour execution sessions with objective convergence detection.

## Table of Contents

1. [What Are Autonomous Agents?](#what-are-autonomous-agents)
2. [Architecture Overview](#architecture-overview)
3. [The Three Agent Types](#the-three-agent-types)
4. [Key Concepts](#key-concepts)
5. [Convergence Detection](#convergence-detection)
6. [When to Use Each Agent](#when-to-use-each-agent)
7. [Quick Start](#quick-start)
8. [Advanced Usage](#advanced-usage)
9. [Best Practices](#best-practices)
10. [Troubleshooting](#troubleshooting)

---

## What Are Autonomous Agents?

**Autonomous agents** are AI agents that can execute complex tasks over multiple cycles without human intervention. They implement the proven `while(tool_calls_exist)` pattern:

```
while tool_calls_exist:
    gather_context()  # Read files, search code
    take_action()     # Edit files, run commands
    verify()          # Check results, run tests
    iterate()         # Update plan, continue
```

### Key Characteristics

1. **Multi-Cycle Execution**: Execute 5-100+ cycles autonomously
2. **Objective Convergence**: Stop based on `tool_calls` field (not hallucinated confidence)
3. **Tool Integration**: Use tools for file operations, command execution, web access
4. **State Persistence**: Save checkpoints for recovery
5. **Planning System**: Decompose complex tasks into structured plans

### Comparison with Single-Shot Agents

| Feature | Single-Shot Agent | Autonomous Agent |
|---------|------------------|------------------|
| Execution | One cycle | Multi-cycle (5-100+) |
| Convergence | After first response | Objective via tool_calls |
| Use Case | Q&A, classification | Coding, research, data analysis |
| Planning | None | TODO-based structured plans |
| Checkpoints | No | Yes (JSONL format) |
| Duration | Seconds | Minutes to hours |

---

## Architecture Overview

All autonomous agents extend `BaseAutonomousAgent`, which itself extends `BaseAgent`. This provides:

- **Tool Calling**: Integrated tool registry and execution
- **Signatures**: Type-safe I/O definitions
- **Memory**: Conversation history and context
- **Strategies**: `MultiCycleStrategy` for iterative execution

### Inheritance Hierarchy

```
BaseAgent (core framework)
    ↓
BaseAutonomousAgent (autonomous patterns)
    ↓
    ├── ClaudeCodeAgent (15-tool coding agent)
    ├── CodexAgent (container-based PR agent)
    └── [Your Custom Agent]
```

### Execution Flow

```
1. execute_autonomously(task)
   ↓
2. create_plan() [if planning_enabled]
   ↓
3. autonomous_loop()
   ├── Cycle 1: gather_context() → take_action() → verify()
   ├── Cycle 2: gather_context() → take_action() → verify()
   ├── ...
   └── Cycle N: converged (tool_calls=[])
   ↓
4. Return result + metadata
```

---

## The Three Agent Types

### 1. BaseAutonomousAgent

**Purpose**: Foundation for all autonomous agents with core agent loop pattern.

**Key Features**:
- Multi-cycle autonomous execution
- TODO-based planning system
- JSONL checkpoint format
- Objective convergence detection
- Configurable max cycles

**Use Cases**:
- Custom autonomous agents
- Research and analysis tasks
- Multi-step workflows

**Example**:
```python
from kaizen.agents.autonomous import BaseAutonomousAgent, AutonomousConfig

config = AutonomousConfig(
    llm_provider="openai",
    model="gpt-4",
    max_cycles=20,
    planning_enabled=True
)

agent = BaseAutonomousAgent(config=config, signature=signature, tools="all"  # Enable 12 builtin tools via MCP
result = await agent.execute_autonomously("Research Python async patterns")
```

### 2. ClaudeCodeAgent

**Purpose**: Implements Claude Code's proven 15-tool autonomous coding architecture.

**Key Features**:
- 15-tool ecosystem (file, search, execution, web, workflow)
- Diff-first workflow (show changes before applying)
- System reminders (combat model drift)
- Context management (92% compression trigger)
- CLAUDE.md project memory
- 100+ cycle sessions (30+ hours)

**Use Cases**:
- Autonomous coding tasks
- Refactoring and code improvements
- Bug fixes with iterative testing
- Long-running development sessions

**Example**:
```python
from kaizen.agents.autonomous import ClaudeCodeAgent, ClaudeCodeConfig

config = ClaudeCodeConfig(
    llm_provider="openai",
    model="gpt-4",
    max_cycles=100,
    context_threshold=0.92,
    enable_diffs=True,
    enable_reminders=True
)

agent = ClaudeCodeAgent(config=config, signature=signature, tools="all"  # Enable 12 builtin tools via MCP
result = await agent.execute_autonomously("Refactor authentication module")
```

### 3. CodexAgent

**Purpose**: Implements Codex's container-based PR generation architecture.

**Key Features**:
- Container-based execution (isolated environment)
- AGENTS.md configuration (project conventions)
- Test-driven iteration (run → parse → fix → repeat)
- Professional PR generation
- Logging and evidence system
- 1-30 minute one-shot workflows

**Use Cases**:
- Autonomous PR generation
- Bug fixes with tests
- Feature implementation with validation
- One-shot development tasks

**Example**:
```python
from kaizen.agents.autonomous import CodexAgent, CodexConfig

config = CodexConfig(
    llm_provider="openai",
    model="gpt-4",
    timeout_minutes=30,
    container_image="python:3.11",
    agents_md_path="AGENTS.md",
    test_command="pytest tests/"
)

agent = CodexAgent(config=config, signature=signature, tools="all"  # Enable 12 builtin tools via MCP
result = await agent.execute_autonomously("Fix bug #123 and add tests")
```

---

## Key Concepts

### 1. Autonomous Loop Pattern

The core pattern is a single-threaded loop that continues until convergence:

```python
async def _autonomous_loop(self, task: str) -> Dict[str, Any]:
    """Autonomous execution loop following while(tool_calls_exist) pattern."""
    for cycle_num in range(self.autonomous_config.max_cycles):
        # Execute cycle using strategy
        cycle_result = self.strategy.execute(self, inputs)

        # Save checkpoint at specified frequency
        if cycle_num % self.autonomous_config.checkpoint_frequency == 0:
            self._save_checkpoint(cycle_result, cycle_num)

        # Check convergence (objective via tool_calls)
        if self._check_convergence(cycle_result):
            return cycle_result

        # Update inputs for next cycle
        inputs["observation"] = cycle_result.get("observation", "")

    return final_result
```

### 2. Planning System

Optional TODO-based planning decomposes complex tasks:

```python
# Generated plan structure
plan = [
    {
        "task": "Design API schema",
        "status": "pending",
        "priority": "high",
        "estimated_cycles": 3
    },
    {
        "task": "Implement endpoints",
        "status": "pending",
        "priority": "high",
        "estimated_cycles": 5
    },
    {
        "task": "Write tests",
        "status": "pending",
        "priority": "medium",
        "estimated_cycles": 2
    }
]
```

### 3. State Persistence

Checkpoints enable recovery from failures:

```python
# Checkpoint saved every N cycles (configurable)
checkpoint_data = {
    "cycle": cycle_num,
    "state": current_state,
    "plan": current_plan,
}

# Saved in JSONL format (one JSON per line)
# File: checkpoints/checkpoint_cycle_005.jsonl
```

### 4. Tool Integration

Autonomous agents use tools for all actions:

```python
# Tools available to agent
tools = [
    "read_file",      # Read file contents
    "write_file",     # Create/overwrite files
    "edit_file",      # Apply diffs to files
    "bash_command",   # Execute shell commands
    "fetch_url",      # HTTP requests
    "web_search",     # Search web
    "glob_search",    # Find files by pattern
    "grep_search",    # Search file contents
    "todo_write",     # Update task list
    # ... and more
]
```

---

## Convergence Detection

### ADR-013: Objective Convergence Detection

Kaizen uses **objective convergence detection** based on the `tool_calls` field from LLM responses, not subjective fields like confidence or action.

#### Why Objective Detection?

| Method | Type | Risk |
|--------|------|------|
| tool_calls field | Objective | ✅ No hallucination |
| confidence score | Subjective | ⚠️ Can hallucinate high confidence |
| action == "finish" | Subjective | ⚠️ Can hallucinate finish action |

#### Implementation

```python
def _check_convergence(self, response: Dict[str, Any]) -> bool:
    """
    Check convergence using objective detection (ADR-013).

    Priority:
    1. Objective (preferred): Check tool_calls field
       - Empty list [] → converged
       - Non-empty list → not converged

    2. Subjective (fallback): Action-based detection
       - action == "finish" → converged
       - confidence > 0.9 → converged
    """
    # OBJECTIVE DETECTION (preferred)
    if "tool_calls" in response:
        tool_calls = response.get("tool_calls")
        if isinstance(tool_calls, list):
            if not tool_calls:  # Empty list
                return True  # Converged
            else:
                return False  # Not converged

    # SUBJECTIVE DETECTION (fallback)
    if response.get("action") == "finish":
        return True

    if response.get("confidence", 0.0) > 0.9:
        return True

    return True  # Default: converged (safe fallback)
```

#### Convergence Example

```python
# Cycle 1: Not converged (has tool calls)
response_1 = {
    "result": "Need to read file",
    "tool_calls": [
        {"name": "read_file", "arguments": {"path": "main.py"}}
    ]
}
converged = agent._check_convergence(response_1)  # False

# Cycle 2: Not converged (has tool calls)
response_2 = {
    "result": "Need to write file",
    "tool_calls": [
        {"name": "write_file", "arguments": {"path": "output.txt", "content": "..."}}
    ]
}
converged = agent._check_convergence(response_2)  # False

# Cycle 3: Converged (no tool calls)
response_3 = {
    "result": "Task completed successfully",
    "tool_calls": []
}
converged = agent._check_convergence(response_3)  # True
```

---

## When to Use Each Agent

### Decision Matrix

| Requirement | BaseAutonomousAgent | ClaudeCodeAgent | CodexAgent |
|-------------|---------------------|-----------------|------------|
| Custom autonomous logic | ✅ Best | ❌ Use BaseAutonomousAgent | ❌ Use BaseAutonomousAgent |
| Autonomous coding tasks | ⚠️ Manual setup | ✅ Best | ⚠️ For PR workflow only |
| Long sessions (30+ hours) | ⚠️ Manual context mgmt | ✅ Best | ❌ 30min max |
| Container isolation | ❌ No | ❌ No | ✅ Best |
| PR generation | ⚠️ Manual | ⚠️ Manual | ✅ Best |
| Project conventions | ⚠️ Manual | ✅ CLAUDE.md | ✅ AGENTS.md |
| Diff visibility | ⚠️ Manual | ✅ Built-in | ⚠️ Manual |
| Test-driven iteration | ⚠️ Manual | ⚠️ Manual | ✅ Built-in |

### Use Case Examples

#### 1. Research and Analysis → BaseAutonomousAgent
```python
task = "Research Python async patterns and create comprehensive summary"
# Needs: Multi-cycle execution, web search, file writing
# Duration: 10-20 cycles
# Best: BaseAutonomousAgent with planning
```

#### 2. Code Refactoring → ClaudeCodeAgent
```python
task = "Refactor authentication module for better testability"
# Needs: Code reading, editing, testing, iteration
# Duration: 30-100 cycles (1-4 hours)
# Best: ClaudeCodeAgent with diff-first workflow
```

#### 3. Bug Fix PR → CodexAgent
```python
task = "Fix bug #123: authentication timeout after 30 minutes"
# Needs: Container isolation, test running, PR generation
# Duration: 10-30 cycles (5-30 minutes)
# Best: CodexAgent with test-driven iteration
```

---

## Quick Start

### Example 1: Basic Autonomous Execution

```python
import asyncio
from kaizen.agents.autonomous import BaseAutonomousAgent, AutonomousConfig
from kaizen.signatures import Signature, InputField, OutputField
# Tools auto-configured via MCP

# Define signature
class ResearchSignature(Signature):
    task: str = InputField(description="Research task")
    context: str = InputField(description="Additional context", default="")
    observation: str = InputField(description="Last observation", default="")

    findings: str = OutputField(description="Research findings")
    next_action: str = OutputField(description="Next action")
    tool_calls: list = OutputField(description="Tool calls", default=[])

# Create configuration
config = AutonomousConfig(
    llm_provider="openai",
    model="gpt-4",
    max_cycles=15,
    planning_enabled=True,
    checkpoint_frequency=5
)

# Create tool registry

# 12 builtin tools enabled via MCP

# Create agent
agent = BaseAutonomousAgent(
    config=config,
    signature=ResearchSignature(),
    tools="all"  # Enable 12 builtin tools via MCP
)

# Execute autonomously
async def main():
    result = await agent.execute_autonomously(
        "Research Python async programming patterns and create summary"
    )

    print(f"✅ Completed in {result['cycles_used']} cycles")
    print(f"Findings: {result.get('findings', 'N/A')}")

asyncio.run(main())
```

### Example 2: ClaudeCodeAgent for Coding

```python
from kaizen.agents.autonomous import ClaudeCodeAgent, ClaudeCodeConfig
from kaizen.signatures import Signature, InputField, OutputField

# Define signature for coding tasks
class CodingSignature(Signature):
    task: str = InputField(description="Coding task")
    context: str = InputField(description="Code context", default="")
    observation: str = InputField(description="Last observation", default="")

    code_changes: str = OutputField(description="Code modifications")
    next_action: str = OutputField(description="Next action")
    tool_calls: list = OutputField(description="Tool calls", default=[])

# Create configuration
config = ClaudeCodeConfig(
    llm_provider="openai",
    model="gpt-4",
    max_cycles=50,
    context_threshold=0.92,
    enable_diffs=True,
    enable_reminders=True,
    claude_md_path="CLAUDE.md"
)

# Create agent
agent = ClaudeCodeAgent(
    config=config,
    signature=CodingSignature(),
    tools="all"  # Enable 12 builtin tools via MCP
)

# Execute autonomously
result = await agent.execute_autonomously(
    "Refactor authentication module to use dependency injection"
)

print(f"✅ Refactoring complete in {result['cycles_used']} cycles")
```

### Example 3: CodexAgent for PR Generation

```python
from kaizen.agents.autonomous import CodexAgent, CodexConfig
from kaizen.signatures import Signature, InputField, OutputField

# Define signature for PR tasks
class PRSignature(Signature):
    task: str = InputField(description="PR task")
    context: str = InputField(description="Repository context", default="")
    observation: str = InputField(description="Test/lint results", default="")

    changes: str = OutputField(description="Code changes")
    pr_description: str = OutputField(description="PR description")
    tool_calls: list = OutputField(description="Tool calls", default=[])

# Create configuration
config = CodexConfig(
    llm_provider="openai",
    model="gpt-4",
    timeout_minutes=30,
    container_image="python:3.11",
    enable_internet=False,
    agents_md_path="AGENTS.md",
    test_command="pytest tests/",
    lint_command="ruff check src/"
)

# Create agent
agent = CodexAgent(
    config=config,
    signature=PRSignature(),
    tools="all"  # Enable 12 builtin tools via MCP
)

# Execute autonomously
result = await agent.execute_autonomously(
    "Fix bug #123: user authentication timeout after 30 minutes"
)

print(f"✅ PR generated in {result['cycles_used']} cycles")
print(f"PR Description:\n{result.get('pr_description', 'N/A')}")
```

---

## Advanced Usage

### Custom Autonomous Agent

Create your own autonomous agent by extending `BaseAutonomousAgent`:

```python
from dataclasses import dataclass
from kaizen.agents.autonomous import BaseAutonomousAgent, AutonomousConfig

@dataclass
class CustomAgentConfig(AutonomousConfig):
    """Configuration for custom autonomous agent."""
    max_cycles: int = 25
    planning_enabled: bool = True
    custom_param: str = "value"

class CustomAutonomousAgent(BaseAutonomousAgent):
    """Custom autonomous agent with specialized behavior."""

    def __init__(
        self,
        config: CustomAgentConfig,
        signature: Signature,
        ,
        **kwargs
    ):
        super().__init__(
            config=config,
            signature=signature,
            tools="all"  # Enable tools via MCP
            **kwargs
        )

        # Custom initialization
        self.custom_param = config.custom_param

    async def _custom_preprocessing(self, task: str) -> str:
        """Custom preprocessing before execution."""
        # Your custom logic here
        return f"Preprocessed: {task}"

    async def execute_autonomously(self, task: str) -> Dict[str, Any]:
        """Override execution with custom preprocessing."""
        # Custom preprocessing
        processed_task = await self._custom_preprocessing(task)

        # Call parent execution
        result = await super().execute_autonomously(processed_task)

        # Custom post-processing
        result["custom_metadata"] = self.custom_param

        return result
```

### Checkpoint Recovery

Load and resume from checkpoint:

```python
# Create agent with checkpoint directory
agent = BaseAutonomousAgent(
    config=config,
    signature=signature,
    tools="all"  # Enable 12 builtin tools via MCP
    checkpoint_dir=Path("./my_checkpoints")
)

# Load checkpoint from specific cycle
checkpoint = agent._load_checkpoint(cycle_num=10)

if checkpoint:
    print(f"Loaded checkpoint from cycle {checkpoint['cycle']}")
    # Resume execution from checkpoint state
    # (Implementation depends on your use case)
else:
    print("No checkpoint found, starting fresh")
```

### Custom Convergence Detection

Override convergence detection for custom logic:

```python
class CustomConvergenceAgent(BaseAutonomousAgent):
    """Agent with custom convergence detection."""

    def _check_convergence(self, response: Dict[str, Any]) -> bool:
        """Custom convergence detection."""
        # Option 1: Use objective detection (recommended)
        if "tool_calls" in response and isinstance(response["tool_calls"], list):
            if not response["tool_calls"]:
                return True  # Converged

        # Option 2: Add custom convergence criteria
        if response.get("custom_done_signal") == "complete":
            return True

        # Option 3: Check task-specific completion
        if "all tests passed" in response.get("observation", "").lower():
            return True

        # Fallback to parent implementation
        return super()._check_convergence(response)
```

### Dynamic Tool Registration

Add tools dynamically during execution:

```python
from kaizen.tools import Tool, ToolParameter

# Create custom tool
custom_tool = Tool(
    name="analyze_code_complexity",
    description="Analyze code complexity metrics",
    parameters=[
        ToolParameter(name="file_path", type="string", required=True, description="Path to file")
    ],
    executor=analyze_complexity_function,
    danger_level="SAFE"
)

# Register tool
agent.tool_registry.register(custom_tool)

# Tool is now available to agent
result = await agent.execute_autonomously("Analyze complexity of main.py")
```

---

## Best Practices

### 1. Choose the Right Agent Type

✅ **DO**: Select agent based on task requirements
```python
# Research task → BaseAutonomousAgent
research_agent = BaseAutonomousAgent(config, signature, registry)

# Coding task → ClaudeCodeAgent
coding_agent = ClaudeCodeAgent(config, signature, registry)

# PR generation → CodexAgent
pr_agent = CodexAgent(config, signature, registry)
```

❌ **DON'T**: Use ClaudeCodeAgent for non-coding tasks
```python
# Wrong: ClaudeCodeAgent for research
agent = ClaudeCodeAgent(...)  # Has unnecessary diff/reminder features
result = await agent.execute_autonomously("Research Python patterns")
```

### 2. Set Appropriate max_cycles

✅ **DO**: Match max_cycles to task complexity
```python
# Simple tasks: 10-20 cycles
config = AutonomousConfig(max_cycles=15)

# Complex tasks: 30-50 cycles
config = AutonomousConfig(max_cycles=40)

# Long-running sessions: 100+ cycles
config = ClaudeCodeConfig(max_cycles=100)
```

❌ **DON'T**: Use excessive cycles for simple tasks
```python
# Wrong: 100 cycles for simple Q&A
config = AutonomousConfig(max_cycles=100)
result = await agent.execute_autonomously("What is Python?")
```

### 3. Enable Planning for Complex Tasks

✅ **DO**: Use planning for multi-step workflows
```python
config = AutonomousConfig(
    max_cycles=30,
    planning_enabled=True  # Enables structured task decomposition
)
```

❌ **DON'T**: Disable planning for complex tasks
```python
# Wrong: No planning for complex task
config = AutonomousConfig(planning_enabled=False)
result = await agent.execute_autonomously(
    "Build REST API with authentication, rate limiting, and monitoring"
)
```

### 4. Configure Checkpoints Appropriately

✅ **DO**: Set checkpoint frequency based on cycle count
```python
# Short tasks (10-20 cycles): checkpoint every 5 cycles
config = AutonomousConfig(max_cycles=15, checkpoint_frequency=5)

# Long tasks (50-100 cycles): checkpoint every 10 cycles
config = ClaudeCodeConfig(max_cycles=100, checkpoint_frequency=10)
```

❌ **DON'T**: Checkpoint too frequently (overhead) or too rarely (data loss)
```python
# Wrong: Checkpoint every cycle (high overhead)
config = AutonomousConfig(checkpoint_frequency=1)

# Wrong: Checkpoint every 50 cycles (lose too much on failure)
config = AutonomousConfig(max_cycles=100, checkpoint_frequency=50)
```

### 5. Use Objective Convergence Detection

✅ **DO**: Rely on tool_calls field for convergence
```python
# Objective detection (recommended)
def _check_convergence(self, response):
    tool_calls = response.get("tool_calls", [])
    return not tool_calls  # Empty list = converged
```

❌ **DON'T**: Use only subjective fields (can hallucinate)
```python
# Wrong: Only subjective detection
def _check_convergence(self, response):
    return response.get("confidence", 0.0) > 0.95  # Can hallucinate
```

### 6. Provide Clear Task Descriptions

✅ **DO**: Provide specific, actionable tasks
```python
task = "Refactor the UserAuthentication class in auth/user.py to use dependency injection. Add unit tests for the new structure."
result = await agent.execute_autonomously(task)
```

❌ **DON'T**: Provide vague or overly broad tasks
```python
# Wrong: Too vague
task = "Improve the code"
result = await agent.execute_autonomously(task)
```

### 7. Monitor Execution Progress

✅ **DO**: Check execution metadata
```python
result = await agent.execute_autonomously(task)

print(f"Cycles used: {result['cycles_used']}/{result['total_cycles']}")
print(f"Converged: {result.get('converged', False)}")
print(f"Plan generated: {len(result.get('plan', [])) > 0}")

if result.get('plan'):
    print("Plan tasks:")
    for task_item in result['plan']:
        print(f"  - {task_item['task']} [{task_item['status']}]")
```

### 8. Handle Errors Gracefully

✅ **DO**: Check for errors in result
```python
result = await agent.execute_autonomously(task)

if result.get('error'):
    print(f"Error occurred: {result['error']}")
    print(f"Failed at cycle: {result.get('cycle', 'unknown')}")
    # Handle error appropriately
else:
    print(f"Success! Result: {result}")
```

---

## Troubleshooting

### Issue 1: Agent Doesn't Converge

**Symptom**: Agent uses all max_cycles without converging

**Causes**:
1. max_cycles set too low for task complexity
2. Task description too vague or complex
3. LLM continues generating tool calls

**Solutions**:

```python
# Solution 1: Increase max_cycles
config = AutonomousConfig(max_cycles=50)  # Was 20

# Solution 2: Break down task
subtasks = [
    "Read and analyze the authentication module",
    "Design refactoring approach",
    "Implement refactoring changes",
    "Add unit tests"
]

for subtask in subtasks:
    result = await agent.execute_autonomously(subtask)

# Solution 3: Add explicit convergence signal in signature
class TaskSignature(Signature):
    task: str = InputField(description="Task to complete")
    done: bool = OutputField(description="True when task fully complete")
    tool_calls: list = OutputField(description="Tool calls", default=[])
```

### Issue 2: Checkpoints Not Saving

**Symptom**: No checkpoint files created

**Causes**:
1. checkpoint_dir doesn't exist or lacks permissions
2. checkpoint_frequency too high
3. Agent fails before first checkpoint

**Solutions**:

```python
# Solution 1: Explicitly create checkpoint directory
from pathlib import Path

checkpoint_dir = Path("./checkpoints")
checkpoint_dir.mkdir(parents=True, exist_ok=True)

agent = BaseAutonomousAgent(
    config=config,
    signature=signature,
    tools="all"  # Enable 12 builtin tools via MCP
    checkpoint_dir=checkpoint_dir
)

# Solution 2: Set lower checkpoint_frequency
config = AutonomousConfig(checkpoint_frequency=2)  # Was 10

# Solution 3: Check file permissions
import os
checkpoint_dir = Path("./checkpoints")
checkpoint_dir.mkdir(parents=True, exist_ok=True)
os.chmod(checkpoint_dir, 0o755)
```

### Issue 3: Tool Calls Not Executing

**Symptom**: Agent reports tool calls but tools don't execute

**Causes**:
1. tool_registry not provided to agent
2. Tools not registered in registry
3. Tool execution errors not caught

**Solutions**:

```python
# Solution 1: Ensure tool_registry is provided
# Tools auto-configured via MCP

# 12 builtin tools enabled via MCP

agent = BaseAutonomousAgent(
    config=config,
    signature=signature,
    tools="all"  # Enable 12 builtin tools via MCP
)

# Solution 2: Verify tools are registered
print(f"Registered tools: {[tool.name for tool in registry.list_tools()]}")

# Solution 3: Add error handling for tool execution
try:
    result = await agent.execute_autonomously(task)
except ToolExecutionError as e:
    print(f"Tool execution failed: {e}")
    print(f"Failed tool: {e.tool_name}")
    print(f"Tool arguments: {e.arguments}")
```

### Issue 4: Planning Not Working

**Symptom**: No plan generated even with planning_enabled=True

**Causes**:
1. Signature missing required fields
2. LLM not generating plan structure
3. Planning disabled in config

**Solutions**:

```python
# Solution 1: Verify planning is enabled
config = AutonomousConfig(planning_enabled=True)  # ← Must be True

# Solution 2: Check signature has required fields
class TaskSignature(Signature):
    task: str = InputField(description="Task description")
    # These fields are optional but help planning:
    context: str = InputField(description="Additional context", default="")

    result: str = OutputField(description="Task result")
    next_action: str = OutputField(description="Next action to take")
    tool_calls: list = OutputField(description="Tool calls", default=[])

# Solution 3: Verify plan in result
result = await agent.execute_autonomously(task)
print(f"Plan generated: {result.get('plan', [])}")

if not result.get('plan'):
    print("Warning: No plan generated")
```

### Issue 5: Context Overflow (ClaudeCodeAgent)

**Symptom**: ClaudeCodeAgent fails with context length error

**Causes**:
1. context_threshold set too high
2. Long files being read without chunking
3. Reminders adding too much context

**Solutions**:

```python
# Solution 1: Lower context_threshold
config = ClaudeCodeConfig(
    context_threshold=0.85  # Was 0.92 (default)
)

# Solution 2: Disable reminders if not needed
config = ClaudeCodeConfig(
    enable_reminders=False  # Reduces context usage
)

# Solution 3: Use context compression
config = ClaudeCodeConfig(
    context_threshold=0.92,
    enable_context_compression=True  # If available
)
```

### Issue 6: Container Execution Fails (CodexAgent)

**Symptom**: CodexAgent fails during container setup

**Causes**:
1. Docker not installed or running
2. Container image not available
3. Container resource limits

**Solutions**:

```python
# Solution 1: Verify Docker is running
import subprocess
try:
    subprocess.run(["docker", "ps"], check=True, capture_output=True)
    print("Docker is running")
except:
    print("Docker not running or not installed")

# Solution 2: Use available container image
config = CodexConfig(
    container_image="python:3.11-slim"  # Smaller image
)

# Solution 3: Increase timeout
config = CodexConfig(
    timeout_minutes=60  # Was 30
)
```

---

## Performance Considerations

### Cycle Duration

Typical cycle durations by agent type:

| Agent Type | Cycles/Minute | Total Duration (20 cycles) |
|------------|---------------|---------------------------|
| BaseAutonomousAgent | 2-4 | 5-10 minutes |
| ClaudeCodeAgent | 1-2 | 10-20 minutes |
| CodexAgent | 1-3 | 7-20 minutes |

### Cost Estimation

Approximate costs for GPT-4 (as of 2025):

| Task Type | Cycles | Tokens/Cycle | Cost/Task |
|-----------|--------|--------------|-----------|
| Simple research | 10 | 2K | $0.20 |
| Code refactoring | 30 | 5K | $1.50 |
| PR generation | 20 | 4K | $0.80 |
| Long session (100 cycles) | 100 | 6K | $6.00 |

**Cost Optimization**:
1. Use smaller models when possible (gpt-3.5-turbo)
2. Enable planning to reduce unnecessary cycles
3. Set appropriate max_cycles to avoid over-execution
4. Use checkpoints to avoid re-execution on failure

---

## Examples

See the following example files for working demonstrations:

1. **`examples/autonomy/01_base_autonomous_agent_demo.py`**
   - Basic autonomous execution with planning
   - Checkpoint saving and recovery
   - Objective convergence detection

2. **`examples/autonomy/02_claude_code_agent_demo.py`**
   - 15-tool ecosystem demonstration
   - Diff-first workflow
   - System reminders and context management

3. **`examples/autonomy/03_codex_agent_demo.py`**
   - Container-based execution
   - AGENTS.md configuration
   - Test-driven iteration and PR generation

---

## References

### Documentation
- **[claude-code-agent.md](claude-code-agent.md)** - ClaudeCodeAgent architecture guide
- **[codex-agent.md](codex-agent.md)** - CodexAgent architecture guide
- **[build-autonomous-agent.md](../tutorials/build-autonomous-agent.md)** - Tutorial for custom agents

### Research
- **[docs/research/CLAUDE_CODE_AUTONOMOUS_ARCHITECTURE.md](../research/CLAUDE_CODE_AUTONOMOUS_ARCHITECTURE.md)** - Claude Code research
- **[docs/research/CODEX_AUTONOMOUS_ARCHITECTURE.md](../research/CODEX_AUTONOMOUS_ARCHITECTURE.md)** - Codex research

### ADRs
- **[ADR-013](../architecture/adr/ADR-013-objective-convergence-detection.md)** - Objective Convergence Detection

### Implementation
- **`src/kaizen/agents/autonomous/base.py`** - BaseAutonomousAgent (532 lines)
- **`src/kaizen/agents/autonomous/claude_code.py`** - ClaudeCodeAgent (691 lines)
- **`src/kaizen/agents/autonomous/codex.py`** - CodexAgent (690 lines)

### Tests
- **`tests/unit/agents/autonomous/test_base_autonomous.py`** - 26 tests
- **`tests/unit/agents/autonomous/test_claude_code.py`** - 38 tests
- **`tests/unit/agents/autonomous/test_codex.py`** - 36 tests

---

## Contributing

To contribute autonomous agent patterns:

1. **Extend BaseAutonomousAgent** for new agent types
2. **Follow objective convergence** using tool_calls field
3. **Add comprehensive tests** (aim for 30+ tests per agent)
4. **Create working examples** demonstrating key features
5. **Document architecture** and use cases

---

## License

MIT License - See LICENSE file for details.

---

**Last Updated**: 2025-10-22
**Version**: 0.1.0
**Status**: Production Ready
