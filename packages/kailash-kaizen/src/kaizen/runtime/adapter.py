"""
Runtime Adapter Abstract Base Class

Defines the RuntimeAdapter interface that all autonomous agent runtime
implementations must follow. This enables runtime-agnostic code while
supporting runtime-specific optimizations.
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from kaizen.runtime.capabilities import RuntimeCapabilities
from kaizen.runtime.context import ExecutionContext, ExecutionResult

# Type alias for progress callback
ProgressCallback = Callable[[str, Dict[str, Any]], None]


class RuntimeAdapter(ABC):
    """Abstract base class for autonomous agent runtime adapters.

    All runtime implementations (Claude Code, OpenAI Codex, Gemini CLI,
    Kaizen Local) must implement this interface to work with the
    Runtime Abstraction Layer.

    The adapter is responsible for:
    1. Translating ExecutionContext to runtime-specific format
    2. Executing the task using the underlying runtime
    3. Normalizing results back to ExecutionResult

    Example:
        >>> class MyRuntimeAdapter(RuntimeAdapter):
        ...     @property
        ...     def capabilities(self) -> RuntimeCapabilities:
        ...         return RuntimeCapabilities(
        ...             runtime_name="my_runtime",
        ...             provider="my_company",
        ...             supports_tool_calling=True,
        ...         )
        ...
        ...     async def execute(self, context, on_progress=None):
        ...         # Implementation here
        ...         return ExecutionResult.from_success("Result", "my_runtime")
    """

    @property
    @abstractmethod
    def capabilities(self) -> RuntimeCapabilities:
        """Return the capabilities of this runtime.

        This property is used by RuntimeSelector to determine if this
        runtime is suitable for a given task.

        Returns:
            RuntimeCapabilities describing what this runtime can do
        """
        pass

    @abstractmethod
    async def execute(
        self,
        context: ExecutionContext,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ExecutionResult:
        """Execute a task using this runtime.

        This is the main entry point for task execution. The adapter should:
        1. Map tools from Kaizen format to runtime-specific format
        2. Execute the task using the underlying runtime
        3. Normalize the result to ExecutionResult

        Args:
            context: Normalized execution context with task, tools, constraints
            on_progress: Optional callback for progress updates.
                         Called with (event_type: str, data: dict)
                         Event types: "thinking", "tool_call", "tool_result", "output"

        Returns:
            ExecutionResult with output, status, tool calls, and metrics
        """
        pass

    @abstractmethod
    async def stream(
        self,
        context: ExecutionContext,
    ) -> AsyncIterator[str]:
        """Stream execution output token by token.

        For runtimes that support streaming, this provides a way to
        receive output incrementally as it's generated.

        Args:
            context: Normalized execution context

        Yields:
            Output tokens/chunks as they're generated

        Raises:
            NotImplementedError: If runtime doesn't support streaming
        """
        pass

    @abstractmethod
    async def interrupt(
        self,
        session_id: str,
        mode: str = "graceful",
    ) -> bool:
        """Interrupt an ongoing execution.

        Args:
            session_id: The session to interrupt
            mode: Interrupt mode:
                  - "graceful": Allow current tool to complete
                  - "immediate": Stop immediately
                  - "rollback": Stop and undo incomplete operations

        Returns:
            True if interrupt was successful, False otherwise
        """
        pass

    @abstractmethod
    def map_tools(
        self,
        kaizen_tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Map tools from Kaizen format to runtime-specific format.

        Different runtimes have different tool schemas:
        - Claude Code: Uses specific tool definitions
        - OpenAI: Uses function calling format
        - Gemini: Uses tools array format

        Args:
            kaizen_tools: Tools in Kaizen/OpenAI function format

        Returns:
            Tools in runtime-specific format
        """
        pass

    @abstractmethod
    def normalize_result(
        self,
        raw_result: Any,
    ) -> ExecutionResult:
        """Normalize runtime-specific result to ExecutionResult.

        Converts the raw output from the underlying runtime to
        the standard ExecutionResult format.

        Args:
            raw_result: Raw result from the runtime

        Returns:
            Normalized ExecutionResult
        """
        pass

    # Optional methods with default implementations

    async def health_check(self) -> bool:
        """Check if the runtime is healthy and available.

        Returns:
            True if runtime is available, False otherwise
        """
        return True

    async def warmup(self) -> None:
        """Perform any warmup operations (e.g., load models, establish connections).

        Called once when the runtime is first used to reduce cold start latency.
        """
        pass

    async def cleanup(self) -> None:
        """Clean up resources (connections, temp files, etc.).

        Called when the runtime is no longer needed.
        """
        pass

    def get_native_tool_names(self) -> List[str]:
        """Get list of native tool names supported by this runtime.

        Returns:
            List of tool names
        """
        return self.capabilities.native_tools

    def supports_model(self, model: str) -> bool:
        """Check if this runtime supports a specific model.

        Args:
            model: Model identifier to check

        Returns:
            True if model is supported
        """
        return model in self.capabilities.supported_models

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(runtime={self.capabilities.runtime_name})"


class BaseRuntimeAdapter(RuntimeAdapter):
    """Base class with common functionality for runtime adapters.

    Provides default implementations and utilities that most adapters
    can use or override as needed.

    This is an abstract class - subclasses must still implement the
    required abstract methods from RuntimeAdapter.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the adapter with optional configuration.

        Args:
            config: Runtime-specific configuration dictionary
        """
        self.config = config or {}
        self._is_initialized = False

    async def ensure_initialized(self) -> None:
        """Ensure the adapter is initialized before use."""
        if not self._is_initialized:
            await self.warmup()
            self._is_initialized = True

    async def stream(self, context: ExecutionContext) -> AsyncIterator[str]:
        """Default stream implementation that wraps execute.

        Subclasses with native streaming should override this.
        """
        if not self.capabilities.supports_streaming:
            raise NotImplementedError(
                f"{self.capabilities.runtime_name} does not support streaming"
            )

        # Default: execute and yield result as single chunk
        result = await self.execute(context)
        yield result.output

    async def interrupt(self, session_id: str, mode: str = "graceful") -> bool:
        """Default interrupt implementation.

        Most runtimes need custom interrupt handling.
        """
        if not self.capabilities.supports_interrupt:
            return False
        # Subclasses should implement actual interrupt logic
        return False

    def map_tools(self, kaizen_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Default tool mapping (pass-through).

        Most runtimes accept OpenAI function calling format which
        Kaizen tools already use.
        """
        return kaizen_tools

    def normalize_result(self, raw_result: Any) -> ExecutionResult:
        """Default result normalization.

        Handles common cases where raw_result is a string or dict.
        Subclasses should override for runtime-specific formats.
        """
        if isinstance(raw_result, ExecutionResult):
            return raw_result

        if isinstance(raw_result, str):
            return ExecutionResult.from_success(
                output=raw_result,
                runtime_name=self.capabilities.runtime_name,
            )

        if isinstance(raw_result, dict):
            return ExecutionResult.from_dict(raw_result)

        return ExecutionResult.from_success(
            output=str(raw_result),
            runtime_name=self.capabilities.runtime_name,
        )
