# Runtime Abstraction Layer Developer Guide

The Runtime Abstraction Layer (TODO-191) provides a unified interface for executing autonomous agent tasks across different backends.

## Core Interfaces

### BaseRuntimeAdapter

The abstract base class that all runtime adapters must implement:

```python
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional
from kaizen.runtime.context import ExecutionContext, ExecutionResult
from kaizen.runtime.capabilities import RuntimeCapabilities

class BaseRuntimeAdapter(ABC):
    """Abstract base class for runtime adapters."""

    @property
    @abstractmethod
    def capabilities(self) -> RuntimeCapabilities:
        """Return the capabilities of this runtime."""
        ...

    @abstractmethod
    async def execute(
        self,
        context: ExecutionContext,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ExecutionResult:
        """Execute a task and return results."""
        ...

    @abstractmethod
    async def stream(
        self,
        context: ExecutionContext,
    ) -> AsyncIterator[str]:
        """Stream output as it's generated."""
        ...

    @abstractmethod
    async def interrupt(
        self,
        session_id: str,
        mode: str = "graceful",
    ) -> bool:
        """Interrupt an ongoing execution."""
        ...

    @abstractmethod
    def map_tools(
        self,
        kaizen_tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Map Kaizen tools to runtime-specific format."""
        ...

    @abstractmethod
    def normalize_result(
        self,
        raw_result: Any,
    ) -> ExecutionResult:
        """Normalize raw results to ExecutionResult."""
        ...
```

### RuntimeCapabilities

Describes what a runtime can do:

```python
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

@dataclass
class RuntimeCapabilities:
    """Capabilities of a runtime adapter."""

    runtime_name: str
    provider: str
    version: str

    # Feature support
    supports_streaming: bool = False
    supports_tool_calling: bool = False
    supports_parallel_tools: bool = False
    supports_vision: bool = False
    supports_audio: bool = False
    supports_code_execution: bool = False
    supports_file_access: bool = False
    supports_web_access: bool = False
    supports_interrupt: bool = False

    # Limits
    max_context_tokens: int = 0
    max_output_tokens: int = 0

    # Cost
    cost_per_1k_input_tokens: float = 0.0
    cost_per_1k_output_tokens: float = 0.0

    # Performance
    typical_latency_ms: int = 0

    # Native tools
    native_tools: List[str] = field(default_factory=list)
    supported_models: List[str] = field(default_factory=list)

    # Extra
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### ExecutionContext

Universal input format for all adapters:

```python
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import uuid

@dataclass
class ExecutionContext:
    """Execution context for runtime adapters."""

    task: str
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Optional configuration
    tools: List[Dict[str, Any]] = field(default_factory=list)
    system_prompt: Optional[str] = None
    memory_context: Optional[str] = None
    files: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Execution limits
    timeout_seconds: Optional[float] = None
    max_tokens: Optional[int] = None
```

### ExecutionResult

Normalized output format:

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

class ExecutionStatus(Enum):
    COMPLETE = "complete"
    ERROR = "error"
    TIMEOUT = "timeout"
    INTERRUPTED = "interrupted"
    PENDING = "pending"

@dataclass
class ExecutionResult:
    """Result of an execution."""

    output: str
    status: ExecutionStatus
    tokens_used: int = 0
    runtime_name: str = ""
    session_id: str = ""

    # Error information
    error_message: Optional[str] = None
    error_type: Optional[str] = None

    # Artifacts
    files_created: List[str] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_success(cls, output: str, runtime_name: str = "") -> "ExecutionResult":
        return cls(output=output, status=ExecutionStatus.COMPLETE, runtime_name=runtime_name)

    @classmethod
    def from_error(cls, error: str, error_type: str = "Error") -> "ExecutionResult":
        return cls(
            output="",
            status=ExecutionStatus.ERROR,
            error_message=error,
            error_type=error_type,
        )
```

## RuntimeSelector

Intelligent runtime selection based on task requirements:

```python
from kaizen.runtime.selector import RuntimeSelector

selector = RuntimeSelector()

# Register adapters
selector.register("local_kaizen", LocalKaizenAdapter())
selector.register("claude_code", ClaudeCodeAdapter())
selector.register("openai_codex", OpenAICodexAdapter())
selector.register("gemini_cli", GeminiCLIAdapter())

# Select by name
adapter = await selector.get_adapter("local_kaizen")

# Select by requirements
adapter = await selector.select_for_task(
    task="Analyze this large document",
    requirements={
        "context_window": "large",  # Needs >100K tokens
        "code_execution": True,
    }
)

# Select by capabilities
adapter = await selector.select_by_capabilities(
    RuntimeCapabilities(
        supports_vision=True,
        supports_audio=True,
        min_context_tokens=500000,
    )
)
```

### Selection Strategies

The RuntimeSelector supports 5 selection strategies:

| Strategy | Description | Use Case |
|----------|-------------|----------|
| `capability_match` | Match required capabilities | Default |
| `cost_optimized` | Minimize cost per token | Budget-conscious |
| `latency_optimized` | Minimize response time | Real-time apps |
| `context_optimized` | Maximize context window | Large documents |
| `feature_complete` | Most capable runtime | Complex tasks |

```python
# Use specific strategy
adapter = await selector.select_for_task(
    task="Quick question",
    strategy="latency_optimized"
)
```

## Implementing a Custom Adapter

### Step 1: Create the Adapter Class

```python
from kaizen.runtime.adapter import BaseRuntimeAdapter, ProgressCallback
from kaizen.runtime.capabilities import RuntimeCapabilities
from kaizen.runtime.context import ExecutionContext, ExecutionResult, ExecutionStatus

class MyCustomAdapter(BaseRuntimeAdapter):
    """Custom adapter for MyService."""

    def __init__(
        self,
        api_key: str,
        model: str = "my-model",
        timeout_seconds: float = 300,
    ):
        super().__init__()
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._client = None
        self._capabilities = self._build_capabilities()

    @property
    def capabilities(self) -> RuntimeCapabilities:
        return self._capabilities

    def _build_capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            runtime_name="my_custom",
            provider="mycompany",
            version="1.0.0",
            supports_streaming=True,
            supports_tool_calling=True,
            max_context_tokens=128000,
            max_output_tokens=4096,
            cost_per_1k_input_tokens=0.01,
            cost_per_1k_output_tokens=0.03,
        )

    async def ensure_initialized(self) -> None:
        """Initialize client if needed."""
        if self._client is None:
            from myservice import AsyncClient
            self._client = AsyncClient(api_key=self.api_key)
        await super().ensure_initialized()

    async def execute(
        self,
        context: ExecutionContext,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ExecutionResult:
        await self.ensure_initialized()

        if on_progress:
            on_progress("starting", {"task": context.task[:100]})

        try:
            response = await self._client.generate(
                model=self.model,
                prompt=context.task,
                tools=self.map_tools(context.tools),
            )

            return ExecutionResult(
                output=response.text,
                status=ExecutionStatus.COMPLETE,
                tokens_used=response.usage.total_tokens,
                runtime_name="my_custom",
                session_id=context.session_id,
            )

        except TimeoutError:
            return ExecutionResult(
                output="",
                status=ExecutionStatus.TIMEOUT,
                error_message=f"Timed out after {self.timeout_seconds}s",
            )

        except Exception as e:
            return ExecutionResult(
                output="",
                status=ExecutionStatus.ERROR,
                error_message=str(e),
                error_type=type(e).__name__,
            )

    async def stream(self, context: ExecutionContext) -> AsyncIterator[str]:
        await self.ensure_initialized()

        async for chunk in self._client.stream(
            model=self.model,
            prompt=context.task,
        ):
            yield chunk.text

    async def interrupt(self, session_id: str, mode: str) -> bool:
        # Implement interrupt logic
        return False

    def map_tools(self, kaizen_tools: List[Dict]) -> List[Dict]:
        # Convert Kaizen format to MyService format
        return [self._convert_tool(t) for t in kaizen_tools]

    def normalize_result(self, raw_result: Any) -> ExecutionResult:
        if isinstance(raw_result, ExecutionResult):
            return raw_result
        return ExecutionResult.from_success(str(raw_result), "my_custom")
```

### Step 2: Register with RuntimeSelector

```python
selector = RuntimeSelector()
selector.register("my_custom", MyCustomAdapter(api_key="..."))

# Now it's available for selection
adapter = await selector.get_adapter("my_custom")
```

### Step 3: Add to Exports (Optional)

If this is a permanent addition:

```python
# src/kaizen/runtime/adapters/__init__.py
from kaizen.runtime.adapters.my_custom import MyCustomAdapter

__all__ = [
    # ... existing exports
    "MyCustomAdapter",
]
```

## Progress Callbacks

Adapters can report progress during execution:

```python
from kaizen.runtime.adapter import ProgressCallback

def my_progress_handler(stage: str, data: Dict[str, Any]) -> None:
    print(f"[{stage}] {data}")

result = await adapter.execute(context, on_progress=my_progress_handler)
```

Common stages:
- `starting` - Task beginning
- `thinking` - LLM reasoning
- `tool_call` - Executing a tool
- `tool_result` - Tool completed
- `generating` - Producing output
- `complete` - Task finished

## Error Handling

All adapters handle errors consistently:

```python
result = await adapter.execute(context)

if result.status == ExecutionStatus.COMPLETE:
    print(f"Success: {result.output}")

elif result.status == ExecutionStatus.ERROR:
    print(f"Error ({result.error_type}): {result.error_message}")

elif result.status == ExecutionStatus.TIMEOUT:
    print(f"Timed out: {result.error_message}")

elif result.status == ExecutionStatus.INTERRUPTED:
    print("Execution was interrupted")
```

## Health Checks

Check if a runtime is available:

```python
from kaizen.runtime.adapters.claude_code import is_claude_code_available
from kaizen.runtime.adapters.openai_codex import is_openai_available
from kaizen.runtime.adapters.gemini_cli import is_gemini_available

# Individual checks
if await is_claude_code_available():
    adapter = ClaudeCodeAdapter()

# Or use RuntimeSelector
available = await selector.get_available_adapters()
print(f"Available: {[a.capabilities.runtime_name for a in available]}")
```

## Best Practices

1. **Always call `ensure_initialized()`** before using the adapter
2. **Handle all ExecutionStatus values** in your error handling
3. **Use progress callbacks** for long-running tasks to provide user feedback
4. **Set appropriate timeouts** for different task types
5. **Implement `interrupt()`** for cancelable operations
6. **Use the RuntimeSelector** for automatic adapter selection
7. **Register custom adapters** with the selector for unified access
