# Runtime Abstraction Layer

The Runtime Abstraction Layer (RAL) provides a unified interface for multiple autonomous agent runtimes, enabling runtime-agnostic code while supporting runtime-specific optimizations.

## Core Concept

Different autonomous agent runtimes (Claude Code, OpenAI Codex, Gemini CLI, Kaizen Native) have varying capabilities, tool formats, and execution models. The RAL normalizes these differences through:

1. **ExecutionContext** - Normalized task input
2. **ExecutionResult** - Normalized execution output
3. **RuntimeAdapter** - Interface each runtime implements
4. **RuntimeSelector** - Intelligent runtime selection

## Components

### ExecutionContext

Describes what to execute:

```python
from kaizen.runtime import ExecutionContext

context = ExecutionContext(
    task="Read the config file and summarize it",
    tools=[{"name": "read_file", "type": "function"}],
    max_cycles=50,
    timeout_seconds=120.0,
    preferred_runtime="claude_code",
)
```

Key fields:
- `task`: The task description (required)
- `tools`: Available tools in OpenAI function calling format
- `memory_context`: Prior context to include
- `conversation_history`: Previous messages
- `max_cycles`: Maximum execution cycles
- `max_tokens`: Output token limit
- `budget_usd`: Cost budget
- `timeout_seconds`: Execution timeout
- `permission_mode`: Tool permission handling
- `preferred_runtime`: Runtime preference

### ExecutionResult

Captures execution outcome:

```python
from kaizen.runtime import ExecutionResult, ExecutionStatus

result = ExecutionResult(
    output="The config contains...",
    status=ExecutionStatus.COMPLETE,
    tokens_used=500,
    cost_usd=0.015,
    cycles_used=3,
    duration_ms=1500.0,
    runtime_name="claude_code",
    tool_calls=[...],
)

if result.is_success:
    print(result.output)
elif result.is_error:
    print(f"Error: {result.error_message}")
```

Status values:
- `COMPLETE` - Task finished successfully
- `INTERRUPTED` - User interrupted
- `ERROR` - Execution error
- `MAX_CYCLES` - Cycle limit reached
- `BUDGET_EXCEEDED` - Cost limit reached
- `TIMEOUT` - Time limit reached

### RuntimeCapabilities

Describes what a runtime can do:

```python
from kaizen.runtime import RuntimeCapabilities

caps = RuntimeCapabilities(
    runtime_name="my_runtime",
    provider="my_company",
    supports_streaming=True,
    supports_tool_calling=True,
    supports_vision=True,
    supports_file_access=True,
    supports_code_execution=True,
    max_context_tokens=100000,
    cost_per_1k_input_tokens=0.01,
    typical_latency_ms=200.0,
    native_tools=["read_file", "bash_command"],
)

# Check capabilities
if caps.supports("vision"):
    # Can process images
    pass

if caps.meets_requirements(["file_access", "code_execution"]):
    # Can handle files and run code
    pass
```

### RuntimeAdapter

Interface for runtime implementations:

```python
from kaizen.runtime import RuntimeAdapter, BaseRuntimeAdapter

class MyRuntimeAdapter(BaseRuntimeAdapter):
    @property
    def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            runtime_name="my_runtime",
            provider="my_company",
            supports_tool_calling=True,
        )

    async def execute(
        self,
        context: ExecutionContext,
        on_progress=None,
    ) -> ExecutionResult:
        # Translate context to runtime-specific format
        # Execute using underlying runtime
        # Return normalized result
        return ExecutionResult.from_success(
            output="Result here",
            runtime_name="my_runtime",
        )
```

Required methods:
- `capabilities` - Return runtime capabilities
- `execute()` - Execute a task
- `stream()` - Stream output (or use default)
- `interrupt()` - Stop execution (or use default)
- `map_tools()` - Convert tool format (or use default pass-through)
- `normalize_result()` - Convert result (or use default)

### RuntimeSelector

Selects the best runtime for a task:

```python
from kaizen.runtime import RuntimeSelector, SelectionStrategy

selector = RuntimeSelector({
    "kaizen_local": kaizen_adapter,
    "claude_code": claude_adapter,
    "openai_codex": openai_adapter,
}, default_runtime="kaizen_local")

# Select based on capability
adapter = selector.select(context, SelectionStrategy.CAPABILITY_MATCH)

# Select cheapest option
adapter = selector.select(context, SelectionStrategy.COST_OPTIMIZED)

# Select fastest option
adapter = selector.select(context, SelectionStrategy.LATENCY_OPTIMIZED)

# Use preferred with fallback
adapter = selector.select(context, SelectionStrategy.PREFERRED)

# Balance cost and latency
adapter = selector.select(context, SelectionStrategy.BALANCED)

# Explain the selection
explanation = selector.explain_selection(context, SelectionStrategy.COST_OPTIMIZED)
print(explanation["reason"])
```

Selection strategies:
- `CAPABILITY_MATCH` - First runtime meeting requirements (prefers default)
- `COST_OPTIMIZED` - Cheapest capable runtime
- `LATENCY_OPTIMIZED` - Fastest capable runtime
- `PREFERRED` - Use preferred if capable, fallback otherwise
- `BALANCED` - Weighted score of cost and latency

## Global Registry

Register and access runtimes globally:

```python
from kaizen.runtime import (
    register_runtime,
    unregister_runtime,
    get_runtime,
    get_all_runtimes,
    list_runtimes,
    set_default_runtime,
    get_default_runtime,
    create_selector,
)

# Register a runtime
register_runtime("my_runtime", my_adapter)

# Get a runtime by name
adapter = get_runtime("my_runtime")

# List all registered runtimes
names = list_runtimes()  # ["my_runtime", "kaizen_local", ...]

# Set and get default
set_default_runtime("kaizen_local")
default = get_default_runtime()

# Create selector with all registered runtimes
selector = create_selector()
```

## Pre-defined Capabilities

Constants for known runtimes:

```python
from kaizen.runtime import (
    KAIZEN_LOCAL_CAPABILITIES,
    CLAUDE_CODE_CAPABILITIES,
    OPENAI_CODEX_CAPABILITIES,
    GEMINI_CLI_CAPABILITIES,
)

# Use as reference for capability definitions
print(CLAUDE_CODE_CAPABILITIES.supports_vision)  # True
print(KAIZEN_LOCAL_CAPABILITIES.native_tools)    # ["read_file", "bash_command", ...]
```

## Implementing a Custom Adapter

```python
from kaizen.runtime import (
    BaseRuntimeAdapter,
    RuntimeCapabilities,
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
    ToolCallRecord,
)

class MyCustomAdapter(BaseRuntimeAdapter):
    """Custom adapter for a specific runtime."""

    def __init__(self, api_key: str):
        super().__init__({"api_key": api_key})
        self._caps = RuntimeCapabilities(
            runtime_name="my_custom",
            provider="my_company",
            supports_streaming=True,
            supports_tool_calling=True,
            supports_vision=False,
            supports_file_access=True,
            cost_per_1k_input_tokens=0.005,
            cost_per_1k_output_tokens=0.015,
            typical_latency_ms=150.0,
            native_tools=["read_file", "write_file"],
        )

    @property
    def capabilities(self) -> RuntimeCapabilities:
        return self._caps

    async def execute(
        self,
        context: ExecutionContext,
        on_progress=None,
    ) -> ExecutionResult:
        await self.ensure_initialized()

        try:
            # Map tools to runtime format
            runtime_tools = self.map_tools(context.tools)

            # Execute using your runtime
            raw_result = await self._call_runtime(
                task=context.task,
                tools=runtime_tools,
                history=context.conversation_history,
            )

            # Track tool calls
            tool_calls = [
                ToolCallRecord(
                    name=call["name"],
                    arguments=call["args"],
                    result=call["result"],
                    status="executed",
                )
                for call in raw_result.get("tool_calls", [])
            ]

            return ExecutionResult(
                output=raw_result["output"],
                status=ExecutionStatus.COMPLETE,
                tokens_used=raw_result.get("tokens"),
                tool_calls=tool_calls,
                runtime_name=self._caps.runtime_name,
            )

        except Exception as e:
            return ExecutionResult.from_error(
                error=e,
                runtime_name=self._caps.runtime_name,
            )

    async def _call_runtime(self, task, tools, history):
        # Your runtime-specific implementation
        pass
```

## Requirement Analysis

The selector analyzes task requirements automatically:

```python
# These tasks are analyzed for capability requirements:

# Vision required (keyword: "image")
ExecutionContext(task="Analyze this image")

# File access required (keyword: "file", "read")
ExecutionContext(task="Read the config file")

# Code execution required (keyword: "run", "bash")
ExecutionContext(task="Run the test suite")

# Web access required (keyword: "fetch", "url")
ExecutionContext(task="Fetch data from the API")

# Interrupt support for long tasks (timeout > 60s)
ExecutionContext(task="Process", timeout_seconds=120.0)
```

Tool names are also analyzed:
- `read_file`, `write_file` -> file_access
- `bash_command`, `shell_exec` -> code_execution
- `web_fetch`, `http_request` -> web_access
- `screenshot`, `vision_tool` -> vision

## Progress Callbacks

Track execution progress:

```python
def on_progress(event_type: str, data: dict):
    if event_type == "thinking":
        print(f"Thinking: {data.get('text')}")
    elif event_type == "tool_call":
        print(f"Calling: {data.get('tool')}")
    elif event_type == "tool_result":
        print(f"Result: {data.get('output')[:100]}...")
    elif event_type == "output":
        print(f"Output: {data.get('text')}")

result = await adapter.execute(context, on_progress=on_progress)
```

## Best Practices

1. **Use the selector** for multi-runtime deployments rather than hardcoding runtime choices
2. **Define capabilities accurately** to ensure proper runtime selection
3. **Handle all status types** in result processing, not just success/error
4. **Track tool calls** for debugging and audit trails
5. **Implement health checks** for production reliability
6. **Use cost/latency metrics** for budget-sensitive applications
