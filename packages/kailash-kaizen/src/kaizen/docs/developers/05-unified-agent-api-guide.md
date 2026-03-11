# Unified Agent API Developer Guide

## Overview

The Unified Agent API provides a progressive configuration interface for Kaizen agents. It allows developers to start with a simple 2-line setup and progressively add capabilities as needed, without changing their mental model or API.

**Key Features:**
- Progressive complexity from beginner to expert
- String shortcuts for common configurations
- Helpful error messages with suggestions
- Type-safe configuration validation
- Pre-built capability presets
- Full expert control when needed

## Quick Start

### Level 1: Dead Simple (2 Lines)

```python
from kaizen.api import Agent

agent = Agent(model="gpt-4")
result = await agent.run("What is IRP?")
print(result.text)
```

### Level 2: Configure Execution Mode

```python
# Single mode (one-shot, default)
agent = Agent(model="gpt-4", execution_mode="single")

# Multi mode (conversational)
agent = Agent(model="gpt-4", execution_mode="multi", max_turns=50)

# Autonomous mode (TAOD loop)
agent = Agent(model="gpt-4", execution_mode="autonomous", max_cycles=100)
```

### Level 3: Add Memory

```python
# Stateless (no memory, default)
agent = Agent(model="gpt-4", memory="stateless")

# Session memory (within conversation)
agent = Agent(model="gpt-4", memory="session")

# Persistent memory (across sessions)
agent = Agent(model="gpt-4", memory="persistent", memory_path="./data/memory")

# Learning memory (with pattern detection)
agent = Agent(model="gpt-4", memory="learning")
```

### Level 4: Add Tools

```python
# No tools (default)
agent = Agent(model="gpt-4", tool_access="none")

# Read-only tools (safe browsing)
agent = Agent(model="gpt-4", tool_access="read_only")

# Constrained tools (with confirmation)
agent = Agent(model="gpt-4", tool_access="constrained")

# Full access (all tools, no confirmation)
agent = Agent(model="gpt-4", tool_access="full")
```

### Level 5: Combined Configuration

```python
agent = Agent(
    model="gpt-4",
    execution_mode="autonomous",
    max_cycles=75,
    memory="session",
    tool_access="constrained",
    timeout_seconds=600.0,
    temperature=0.5,
)
```

## Core Types

### ExecutionMode

Controls how the agent executes tasks:

| Mode | Description | Use Case |
|------|-------------|----------|
| `single` | One-shot execution | Simple Q&A, single tasks |
| `multi` | Multi-turn conversation | Chat, tutoring, discussions |
| `autonomous` | TAOD loop (Think-Act-Observe-Decide) | Complex tasks, coding, research |

```python
from kaizen.api.types import ExecutionMode

# Using string
agent = Agent(model="gpt-4", execution_mode="autonomous")

# Using enum
agent = Agent(model="gpt-4", execution_mode=ExecutionMode.AUTONOMOUS)
```

### MemoryDepth

Controls memory persistence:

| Level | Description | Use Case |
|-------|-------------|----------|
| `stateless` | No memory (default) | One-off tasks |
| `session` | Within conversation | Chat sessions |
| `persistent` | Across sessions | Long-term assistants |
| `learning` | With pattern detection | Personalized agents |

### ToolAccess

Controls tool permissions:

| Level | Description | Tools Available |
|-------|-------------|-----------------|
| `none` | No tools (default) | None |
| `read_only` | Safe read operations | read, glob, grep, search, fetch |
| `constrained` | Safe operations + confirmation | read, write, edit, api calls |
| `full` | All tools, no confirmation | Everything |

## AgentResult

Every agent execution returns an `AgentResult` with comprehensive information:

```python
result = await agent.run("Write a function to sort a list")

# Primary output
print(result.text)

# Status checking
if result.succeeded:
    print("Success!")
elif result.failed:
    print(f"Failed: {result.error}")
elif result.was_interrupted:
    print("User interrupted")

# Execution metrics
print(f"Cycles: {result.cycles}")
print(f"Turns: {result.turns}")
print(f"Duration: {result.duration_seconds}s")

# Token usage
print(f"Input tokens: {result.input_tokens}")
print(f"Output tokens: {result.output_tokens}")
print(f"Total tokens: {result.total_tokens}")

# Cost tracking
print(f"Estimated cost: ${result.cost:.4f}")

# Tool call history
for call in result.tool_calls:
    status = "ok" if call.succeeded else "failed"
    print(f"{call.name}: {status} ({call.duration_ms}ms)")
```

### Tool Call Inspection

```python
# Get specific tool calls
read_calls = result.get_tool_calls_by_name("read")

# Get last tool call
last_call = result.get_last_tool_call()

# Get tool results
results = result.get_tool_results("read")

# Filter by status
successful = result.successful_tool_calls
failed = result.failed_tool_calls
```

### Serialization

```python
# To dictionary
data = result.to_dict()

# To JSON
json_str = result.to_json()

# From dictionary
result = AgentResult.from_dict(data)

# From JSON
result = AgentResult.from_json(json_str)
```

### Factory Methods

```python
# Create success result
result = AgentResult.success(text="Done!", cost=0.01)

# Create error result
result = AgentResult.from_error(error_message="Connection failed", error_type="NetworkError")

# Create timeout result
result = AgentResult.timeout(partial_text="Partial output...")

# Create interrupted result
result = AgentResult.interrupted(partial_text="User cancelled")
```

## Capability Presets

Pre-configured agents for common use cases:

```python
from kaizen.api import Agent
from kaizen.api.presets import preset, CapabilityPresets

# Using the preset() function
config = preset("developer")
agent = Agent(model="gpt-4", **config)

# Using CapabilityPresets class
config = CapabilityPresets.developer(max_cycles=200)

# List available presets
presets = CapabilityPresets.list_presets()
for name, description in presets.items():
    print(f"{name}: {description}")
```

### Available Presets

| Preset | Mode | Memory | Tools | Description |
|--------|------|--------|-------|-------------|
| `qa_assistant` | single | stateless | none | Simple Q&A assistant |
| `tutor` | multi | session | none | Educational tutoring |
| `researcher` | autonomous | session | read_only | Research tasks |
| `developer` | autonomous | session | constrained | Software development |
| `admin` | autonomous | persistent | full | System administration |
| `chat_assistant` | multi | persistent | none | Long-term chat companion |
| `data_analyst` | autonomous | session | constrained | Data analysis |
| `code_reviewer` | autonomous | session | read_only | Code review |
| `custom` | - | - | - | Custom configuration |

### Using Presets with AgentConfig

```python
from kaizen.api.config import AgentConfig

# Create config from preset
config = AgentConfig.from_preset("developer", max_cycles=200)

# Create agent
agent = Agent(config=config)
```

## Expert Configuration

For full control, use `AgentConfig`:

```python
from kaizen.api.config import AgentConfig, CheckpointConfig, HookConfig, LLMRoutingConfig
from kaizen.api.types import ExecutionMode, ToolAccess

config = AgentConfig(
    # Model settings
    model="claude-3-opus",
    provider="anthropic",

    # Execution settings
    execution_mode=ExecutionMode.AUTONOMOUS,
    max_cycles=200,
    max_turns=100,
    max_tool_calls=500,
    timeout_seconds=1800.0,

    # Memory settings
    memory="persistent",
    memory_path="/data/agent_memory",

    # Tool settings
    tool_access=ToolAccess.CONSTRAINED,
    allowed_tools=["read", "write", "python"],

    # Model parameters
    temperature=0.5,
    system_prompt="You are an expert software engineer.",

    # Metadata
    name="CodeAssistant",
    description="Advanced coding assistant",
    tags=["coding", "development"],
)

agent = Agent(config=config)
```

### Checkpoint Configuration

```python
checkpoint = CheckpointConfig(
    enabled=True,
    strategy="on_cycle",  # or "periodic", "manual"
    interval_cycles=5,
    storage_path="/tmp/checkpoints",
    max_checkpoints=10,
    compress=True,
)

config = AgentConfig(
    model="gpt-4",
    checkpoint=checkpoint,
)
```

### Hook Configuration

```python
def on_start(ctx):
    print(f"Agent started: {ctx.session_id}")

def on_cycle(ctx):
    print(f"Cycle {ctx.cycle}: {ctx.action}")

def on_error(ctx):
    print(f"Error: {ctx.error}")

def on_complete(ctx):
    print(f"Completed in {ctx.duration_ms}ms")

hooks = HookConfig(
    on_start=on_start,
    on_cycle=on_cycle,
    on_error=on_error,
    on_complete=on_complete,
)

config = AgentConfig(
    model="gpt-4",
    hooks=hooks,
)
```

### LLM Routing Configuration

```python
routing = LLMRoutingConfig(
    enabled=True,
    strategy="cost_optimized",  # or "balanced", "quality_first"
    task_model_mapping={
        "simple": "gpt-3.5-turbo",
        "complex": "gpt-4",
        "creative": "claude-3-opus",
    },
    fallback_chain=["gpt-4", "claude-3-opus", "gpt-3.5-turbo"],
    max_retries=3,
)

config = AgentConfig(
    model="gpt-4",
    llm_routing=routing,
)
```

## Validation & Error Handling

The API provides helpful error messages with suggestions:

```python
from kaizen.api.validation import ConfigurationError

try:
    agent = Agent(model="gpt-4", execution_mode="invalid")
except ConfigurationError as e:
    print(f"Error: {e.message}")
    print(f"Field: {e.field}")
    print(f"Value: {e.value}")
    print(f"Suggestions: {e.suggestions}")
```

### Programmatic Validation

```python
from kaizen.api.validation import (
    validate_configuration,
    validate_model_runtime_compatibility,
    validate_capability_consistency,
    get_recommended_configuration,
)

# Validate full configuration
is_valid, errors = validate_configuration(
    model="gpt-4",
    runtime="local",
    execution_mode="autonomous",
    memory="session",
    tool_access="constrained",
)

if not is_valid:
    for error in errors:
        print(f"Error: {error.message}")

# Validate model-runtime compatibility
is_valid, error = validate_model_runtime_compatibility("gpt-4", "claude_code")
# Returns False with helpful error about incompatibility

# Get recommended configuration for a task
config = get_recommended_configuration("Implement a REST API endpoint")
# Returns: {"execution_mode": "autonomous", "tool_access": "constrained", ...}
```

## Agent Methods

### run()

Execute a task and return the result:

```python
result = await agent.run("What is the capital of France?")
print(result.text)
```

### stream()

Stream output tokens as they're generated:

```python
async for chunk in agent.stream("Write a poem about AI"):
    print(chunk, end="", flush=True)
```

### chat()

Conversational multi-turn interaction:

```python
agent = Agent(model="gpt-4", memory="session")

result = await agent.chat("My name is Alice")
print(result.text)  # "Hello Alice!"

result = await agent.chat("What's my name?")
print(result.text)  # "Your name is Alice"
```

### State Management

```python
# Reset session (new session ID)
agent.reset()

# Pause autonomous execution
agent.pause()

# Resume paused execution
agent.resume()

# Stop execution
agent.stop()

# Mode switching (returns self for chaining)
agent.set_mode("autonomous").run("complex task")
```

## Model Aliases

The API supports convenient model aliases:

| Alias | Resolves To |
|-------|-------------|
| `gpt4` | `gpt-4` |
| `gpt4o` | `gpt-4o` |
| `claude` | `claude-3-sonnet` |
| `sonnet` | `claude-3-sonnet` |
| `opus` | `claude-3-opus` |
| `haiku` | `claude-3-haiku` |
| `gemini` | `gemini-1.5-pro` |
| `llama` | `llama3.2` |

```python
# These are equivalent:
agent = Agent(model="gpt4")
agent = Agent(model="gpt-4")
```

## Best Practices

### 1. Start Simple, Add Complexity

```python
# Start with the basics
agent = Agent(model="gpt-4")
result = await agent.run("Hello")

# Add features as needed
agent = Agent(
    model="gpt-4",
    execution_mode="multi",
    memory="session",
)
```

### 2. Use Presets for Common Patterns

```python
# Instead of manual configuration
config = preset("developer")
agent = Agent(model="gpt-4", **config)
```

### 3. Handle Errors Gracefully

```python
try:
    result = await agent.run(task)
    if result.succeeded:
        process_result(result.text)
    else:
        handle_failure(result.error)
except ConfigurationError as e:
    fix_configuration(e.suggestions)
```

### 4. Monitor Costs

```python
result = await agent.run(task)
if result.cost > budget_threshold:
    alert_budget_exceeded(result.cost)
```

### 5. Use Appropriate Tool Access

```python
# Don't give full access when read_only is enough
agent = Agent(model="gpt-4", tool_access="read_only")  # Safer
```

## Architecture

```
kaizen.api/
├── __init__.py          # Public exports
├── types.py             # ExecutionMode, MemoryDepth, ToolAccess, AgentCapabilities
├── result.py            # AgentResult, ToolCallRecord
├── shortcuts.py         # String shortcut resolution
├── validation.py        # ConfigurationError, validators
├── presets.py           # CapabilityPresets
├── config.py            # AgentConfig, CheckpointConfig, HookConfig
└── agent.py             # Main Agent class
```

## API Reference

### Agent Class

```python
class Agent:
    def __init__(
        self,
        model: Optional[str] = None,
        *,
        execution_mode: Union[str, ExecutionMode] = "single",
        max_cycles: int = 100,
        max_turns: int = 50,
        timeout_seconds: float = 300.0,
        memory: Union[str, Any, None] = "stateless",
        memory_path: Optional[str] = None,
        tool_access: Union[str, ToolAccess] = "none",
        tools: Optional[List[Any]] = None,
        allowed_tools: Optional[List[str]] = None,
        denied_tools: Optional[List[str]] = None,
        runtime: Union[str, Any] = "local",
        llm_routing: Optional[Dict[str, str]] = None,
        routing_strategy: str = "balanced",
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        config: Optional[AgentConfig] = None,
    )

    # Methods
    async def run(self, task: str, ...) -> AgentResult
    async def stream(self, task: str, ...) -> AsyncIterator[str]
    async def chat(self, message: str, ...) -> AgentResult
    def reset(self) -> None
    def pause(self) -> None
    def resume(self) -> None
    def stop(self) -> None
    def set_mode(self, mode: Union[str, ExecutionMode]) -> Agent

    # Properties
    @property
    def model(self) -> str
    @property
    def execution_mode(self) -> ExecutionMode
    @property
    def capabilities(self) -> AgentCapabilities
    @property
    def session_id(self) -> str
    @property
    def is_running(self) -> bool
    @property
    def is_paused(self) -> bool
```

### AgentCapabilities Class

```python
@dataclass
class AgentCapabilities:
    execution_modes: List[ExecutionMode]
    max_memory_depth: MemoryDepth
    tool_access: ToolAccess
    max_cycles: int
    max_turns: int
    max_tool_calls: int
    timeout_seconds: float
    allowed_tools: Optional[List[str]]
    denied_tools: Optional[List[str]]

    def can_execute(self, mode: ExecutionMode) -> bool
    def can_use_tool(self, tool_name: str) -> bool
    def get_available_tools(self) -> List[str]
    def requires_confirmation(self, tool_name: str) -> bool
```

## Related Documentation

- [00-native-tools-guide.md](./00-native-tools-guide.md) - Native tool system
- [01-runtime-abstraction-guide.md](./01-runtime-abstraction-guide.md) - Runtime abstraction layer
- [02-local-kaizen-adapter-guide.md](./02-local-kaizen-adapter-guide.md) - LocalKaizenAdapter
- [03-memory-provider-guide.md](./03-memory-provider-guide.md) - Memory providers
- [04-multi-llm-routing-guide.md](./04-multi-llm-routing-guide.md) - Multi-LLM routing
