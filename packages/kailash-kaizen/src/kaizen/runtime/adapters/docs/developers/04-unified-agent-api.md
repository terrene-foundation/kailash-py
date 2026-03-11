# Unified Agent API Developer Guide

The Unified Agent API (TODO-195) provides a developer-friendly interface for creating and configuring autonomous agents with progressive configuration options.

## Overview

The Unified Agent API simplifies agent creation with:

- **3-Axis Capability Model**: execution_mode, memory_depth, tool_access
- **String Shortcuts**: "session", "persistent", "claude_code", "local"
- **Capability Presets**: Pre-configured agents for common use cases
- **Progressive Configuration**: Start simple, add complexity as needed
- **Helpful Validation**: Clear error messages for invalid configurations

## Quick Start

### Simplest Usage

```python
from kaizen.agent import Agent

# Create agent with defaults
agent = Agent()
result = await agent.run("What is 2 + 2?")
print(result.output)
```

### Using Presets

```python
# Pre-configured for specific use cases
agent = Agent.with_preset("developer")
result = await agent.run("Fix the bug in src/main.py")

# Available presets
agent = Agent.with_preset("qa_assistant")     # Quick Q&A
agent = Agent.with_preset("researcher")       # Deep research
agent = Agent.with_preset("tutor")            # Teaching/explaining
agent = Agent.with_preset("developer")        # Code development
agent = Agent.with_preset("data_analyst")     # Data analysis
agent = Agent.with_preset("creative_writer")  # Content creation
agent = Agent.with_preset("code_reviewer")    # Code review
agent = Agent.with_preset("documentation")    # Doc writing
agent = Agent.with_preset("debug_assistant")  # Debugging
```

### Manual Configuration

```python
agent = Agent(
    execution_mode="autonomous",  # or "interactive", "single_shot"
    memory_depth="session",       # or "turn", "persistent"
    tool_access="full",           # or "none", "limited", "sandboxed"
)
```

## Capability Axes

### 1. Execution Mode

Controls how the agent processes tasks:

| Mode | Description | Use Case |
|------|-------------|----------|
| `single_shot` | One response, no iteration | Simple Q&A |
| `interactive` | User feedback between steps | Collaborative work |
| `autonomous` | Full TAOD loop until completion | Complex tasks |

```python
# Single-shot: Quick answers
agent = Agent(execution_mode="single_shot")
result = await agent.run("What is the capital of France?")

# Interactive: User in the loop
agent = Agent(execution_mode="interactive")
async for step in agent.run_interactive("Write a story"):
    print(step.output)
    if await user_wants_changes():
        agent.provide_feedback("Make it funnier")

# Autonomous: Full autonomy
agent = Agent(execution_mode="autonomous")
result = await agent.run("Refactor this entire module")
```

### 2. Memory Depth

Controls how much context the agent retains:

| Depth | Description | Use Case |
|-------|-------------|----------|
| `turn` | Only current turn | Stateless operations |
| `session` | Current session (default) | Conversational tasks |
| `persistent` | Across sessions | Long-term projects |

```python
# Turn-based: No memory between calls
agent = Agent(memory_depth="turn")

# Session: Remembers conversation
agent = Agent(memory_depth="session")
await agent.run("My name is Alice")
await agent.run("What is my name?")  # "Your name is Alice"

# Persistent: Cross-session memory
agent = Agent(
    memory_depth="persistent",
    memory_provider=HierarchicalMemory(storage_path="./memory")
)
```

### 3. Tool Access

Controls what tools the agent can use:

| Access | Description | Use Case |
|--------|-------------|----------|
| `none` | No tools | Pure conversation |
| `limited` | Read-only tools | Safe exploration |
| `sandboxed` | Sandboxed execution | Untrusted code |
| `full` | All available tools | Trusted development |

```python
# No tools: Pure conversation
agent = Agent(tool_access="none")

# Limited: Read-only (no Write, Edit, Bash)
agent = Agent(tool_access="limited")

# Sandboxed: Isolated execution environment
agent = Agent(tool_access="sandboxed")

# Full: All tools available
agent = Agent(tool_access="full")
```

## Capability Presets

### qa_assistant

Quick question answering with minimal overhead.

```python
agent = Agent.with_preset("qa_assistant")
# Equivalent to:
agent = Agent(
    execution_mode="single_shot",
    memory_depth="turn",
    tool_access="none",
)
```

### researcher

Deep research with web access and memory.

```python
agent = Agent.with_preset("researcher")
# Equivalent to:
agent = Agent(
    execution_mode="autonomous",
    memory_depth="session",
    tool_access="limited",  # Read, search, web
)
```

### developer

Full development capabilities.

```python
agent = Agent.with_preset("developer")
# Equivalent to:
agent = Agent(
    execution_mode="autonomous",
    memory_depth="session",
    tool_access="full",  # Read, Write, Edit, Bash
)
```

### data_analyst

Data analysis with sandboxed code execution.

```python
agent = Agent.with_preset("data_analyst")
# Equivalent to:
agent = Agent(
    execution_mode="autonomous",
    memory_depth="session",
    tool_access="sandboxed",  # Code Interpreter
)
```

## Runtime Selection

### String Shortcuts

```python
# Use Claude Code runtime
agent = Agent(runtime="claude_code")

# Use local Kaizen runtime (default)
agent = Agent(runtime="local")

# Use OpenAI Codex
agent = Agent(runtime="openai_codex")

# Use Gemini
agent = Agent(runtime="gemini")
```

### Explicit Runtime

```python
from kaizen.runtime.adapters import LocalKaizenAdapter, ClaudeCodeAdapter

# Custom-configured adapter
adapter = LocalKaizenAdapter(
    config=AutonomousConfig(
        model="gpt-4o",
        max_cycles=100,
    )
)

agent = Agent(runtime=adapter)
```

## AgentCapabilities

The underlying capability representation:

```python
from kaizen.agent.capabilities import AgentCapabilities

caps = AgentCapabilities(
    execution_mode="autonomous",
    memory_depth="session",
    tool_access="full",
    max_cycles=100,
    budget_limit=10.0,
    timeout_seconds=3600,
)

# Validate capabilities
caps.validate()  # Raises if invalid

# Check specific capabilities
if caps.can_execute_code:
    print("Agent can run code")

if caps.can_access_web:
    print("Agent can access the web")
```

## Configuration Validation

The API provides helpful error messages:

```python
try:
    agent = Agent(
        execution_mode="invalid",
    )
except ValueError as e:
    print(e)
    # "execution_mode must be one of: single_shot, interactive, autonomous"

try:
    agent = Agent(
        execution_mode="autonomous",
        tool_access="none",  # Autonomous needs tools
    )
except ValueError as e:
    print(e)
    # "autonomous execution_mode requires tool_access of 'limited' or higher"
```

## AgentResult

Results from agent execution:

```python
result = await agent.run("Fix the bug")

# Core fields
print(result.output)        # Final output text
print(result.status)        # ExecutionStatus enum
print(result.tokens_used)   # Total tokens consumed

# Execution details
print(result.cycles)        # Number of TAOD cycles
print(result.tool_calls)    # List of tool invocations
print(result.files_created) # Files written

# Errors
if result.status == ExecutionStatus.ERROR:
    print(result.error_message)
    print(result.error_type)
```

## Advanced Configuration

### Custom Model

```python
agent = Agent(
    model="claude-3-opus-20240229",
    execution_mode="autonomous",
)
```

### Budget Limits

```python
agent = Agent(
    execution_mode="autonomous",
    budget_limit=5.0,  # Max $5 spend
)
```

### Timeout

```python
agent = Agent(
    execution_mode="autonomous",
    timeout_seconds=3600,  # 1 hour max
)
```

### Custom Tools

```python
from kaizen.tools import BaseTool

class MyTool(BaseTool):
    name = "my_tool"
    description = "Does something custom"

    async def execute(self, **kwargs) -> str:
        return "Result"

agent = Agent(
    execution_mode="autonomous",
    additional_tools=[MyTool()],
)
```

### Memory Provider

```python
from kaizen.runtime.memory import HierarchicalMemory

memory = HierarchicalMemory(
    hot_capacity=100,
    warm_capacity=1000,
    cold_capacity=10000,
    storage_path="./agent_memory",
)

agent = Agent(
    memory_depth="persistent",
    memory_provider=memory,
)
```

## Streaming

```python
# Stream output as it's generated
async for chunk in agent.stream("Write a long story"):
    print(chunk, end="", flush=True)

# Stream with progress callbacks
def on_progress(stage, data):
    print(f"[{stage}] {data}")

await agent.run("Complex task", on_progress=on_progress)
```

## Interruption

```python
import asyncio

# Start task
task = asyncio.create_task(agent.run("Long running task"))

# Later, interrupt
success = await agent.interrupt(mode="graceful")

if success:
    print("Agent stopped gracefully")
```

## Session Management

```python
# Create agent with session
agent = Agent(session_id="my-session")

# Continue session later
agent = Agent(session_id="my-session", resume=True)

# Get session info
info = agent.session_info
print(f"Session: {info.session_id}")
print(f"Started: {info.started_at}")
print(f"Cycles: {info.total_cycles}")
```

## Best Practices

1. **Start with presets** - They're tuned for common use cases
2. **Use appropriate tool_access** - Don't give full access unless needed
3. **Set budget limits** - Protect against runaway costs
4. **Handle errors** - Check result.status before using output
5. **Use streaming** for long tasks - Better user experience
6. **Consider memory needs** - session is usually sufficient

```python
# Good: Appropriate configuration for task
agent = Agent.with_preset("qa_assistant")  # Simple question

# Better: Customize preset for specific needs
agent = Agent(
    **Agent.preset("developer"),
    budget_limit=5.0,
    timeout_seconds=1800,
)
```
