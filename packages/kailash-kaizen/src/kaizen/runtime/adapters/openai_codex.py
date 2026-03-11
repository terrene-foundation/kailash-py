"""
OpenAICodexAdapter - OpenAI Responses API Integration

Delegates autonomous execution to OpenAI's Responses API, leveraging:
- Code Interpreter: Sandboxed Python execution environment
- File Search: Vector store-based file retrieval
- Function Calling: Custom tool execution

This adapter provides a Kaizen-compatible interface to OpenAI's
autonomous code execution capabilities.

Usage:
    >>> from kaizen.runtime.adapters.openai_codex import OpenAICodexAdapter
    >>> from kaizen.runtime.context import ExecutionContext
    >>>
    >>> adapter = OpenAICodexAdapter(api_key="sk-...")
    >>> context = ExecutionContext(task="Analyze this CSV data")
    >>> result = await adapter.execute(context)
"""

import asyncio
import json
import logging
import os
from typing import Any, AsyncIterator, Dict, List, Optional

from kaizen.runtime.adapter import BaseRuntimeAdapter, ProgressCallback
from kaizen.runtime.adapters.tool_mapping import OpenAIToolMapper
from kaizen.runtime.capabilities import RuntimeCapabilities
from kaizen.runtime.context import ExecutionContext, ExecutionResult, ExecutionStatus

logger = logging.getLogger(__name__)


class OpenAICodexAdapter(BaseRuntimeAdapter):
    """Adapter that delegates to OpenAI Responses API.

    OpenAI Responses API provides:
    - Code Interpreter: Sandboxed Python execution with file I/O
    - File Search: RAG over uploaded files
    - Function Calling: Custom tools via function schemas

    This adapter wraps these capabilities in the RuntimeAdapter interface,
    allowing seamless integration with Kaizen's runtime selection.

    Key Features:
        - Sandboxed code execution (safer than local bash)
        - Built-in data analysis libraries (pandas, numpy, matplotlib)
        - Persistent file storage across turns
        - Automatic cleanup of resources

    Limitations:
        - No direct file system access (must upload files)
        - Limited to Python (no bash/shell)
        - Internet access restricted
        - Session-based (not persistent)

    Example:
        >>> adapter = OpenAICodexAdapter(
        ...     api_key=os.environ["OPENAI_API_KEY"],
        ...     enable_code_interpreter=True,
        ... )
        >>>
        >>> context = ExecutionContext(
        ...     task="Analyze sales.csv and create a chart",
        ...     files=["sales.csv"],
        ... )
        >>> result = await adapter.execute(context)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o",
        enable_code_interpreter: bool = True,
        enable_file_search: bool = False,
        custom_tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_completion_tokens: int = 4096,
        timeout_seconds: float = 300,
    ):
        """Initialize the OpenAICodexAdapter.

        Args:
            api_key: OpenAI API key. If not provided, reads from
                    OPENAI_API_KEY environment variable.
            model: Model to use. Must support the Responses API.
                  Default: gpt-4o
            enable_code_interpreter: Enable Code Interpreter tool for
                                    sandboxed Python execution.
            enable_file_search: Enable file search tool for RAG.
            custom_tools: Custom function tools to add.
            temperature: Sampling temperature.
            max_completion_tokens: Maximum tokens for response.
            timeout_seconds: Execution timeout.
        """
        super().__init__()

        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model
        self.enable_code_interpreter = enable_code_interpreter
        self.enable_file_search = enable_file_search
        self.custom_tools = custom_tools or []
        self.temperature = temperature
        self.max_completion_tokens = max_completion_tokens
        self.timeout_seconds = timeout_seconds

        # OpenAI client (lazily initialized)
        self._client: Optional[Any] = None

        # Session tracking
        self._current_session_id: Optional[str] = None
        self._uploaded_files: Dict[str, str] = {}  # filename -> file_id

        # Build capabilities
        self._capabilities = self._build_capabilities()

    @property
    def capabilities(self) -> RuntimeCapabilities:
        """Return OpenAI Codex capabilities."""
        return self._capabilities

    def _build_capabilities(self) -> RuntimeCapabilities:
        """Build capabilities description."""
        native_tools = []
        if self.enable_code_interpreter:
            native_tools.append("code_interpreter")
        if self.enable_file_search:
            native_tools.append("file_search")

        return RuntimeCapabilities(
            runtime_name="openai_codex",
            provider="openai",
            version="2.0.0",
            supports_streaming=True,
            supports_tool_calling=True,
            supports_parallel_tools=True,  # OpenAI supports parallel tool calls
            supports_vision=True,  # GPT-4o supports vision
            supports_audio=False,
            supports_code_execution=self.enable_code_interpreter,
            supports_file_access=True,  # Via file upload
            supports_web_access=False,  # Sandboxed
            supports_interrupt=True,
            max_context_tokens=128000,  # GPT-4o context
            max_output_tokens=self.max_completion_tokens,
            cost_per_1k_input_tokens=5.0,  # GPT-4o pricing
            cost_per_1k_output_tokens=15.0,
            typical_latency_ms=1000,
            native_tools=native_tools,
            supported_models=[
                "gpt-4o",
                "gpt-4o-mini",
                "gpt-4-turbo",
                "gpt-4",
            ],
            metadata={
                "code_interpreter": self.enable_code_interpreter,
                "file_search": self.enable_file_search,
                "sandboxed": True,
            },
        )

    async def ensure_initialized(self) -> None:
        """Ensure OpenAI client is initialized."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(api_key=self.api_key)
            except ImportError:
                raise ImportError(
                    "OpenAI package not installed. Install with: pip install openai"
                )

        await super().ensure_initialized()

    async def execute(
        self,
        context: ExecutionContext,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ExecutionResult:
        """Execute a task using OpenAI Responses API.

        Uses the Responses API which provides:
        - Multi-turn conversations
        - Code Interpreter for Python execution
        - File handling and retrieval

        Args:
            context: Execution context with task and optional files
            on_progress: Progress callback

        Returns:
            ExecutionResult with output and metrics
        """
        await self.ensure_initialized()

        self._current_session_id = context.session_id

        if on_progress:
            on_progress("starting", {"task": context.task[:100]})

        try:
            # Build tools list
            tools = self._build_tools(context)

            # Build input with optional file references
            input_content = self._build_input(context)

            logger.info(
                f"Executing OpenAI Codex: {context.task[:50]}..., "
                f"model: {self.model}"
            )

            if on_progress:
                on_progress("calling_api", {"model": self.model})

            # Use the new Responses API
            response = await self._client.responses.create(
                model=self.model,
                input=input_content,
                tools=tools if tools else None,
                temperature=self.temperature,
                max_output_tokens=self.max_completion_tokens,
            )

            # Extract output
            output = self._extract_output(response)
            tokens_used = self._extract_token_usage(response)

            if on_progress:
                on_progress("complete", {"output_length": len(output)})

            return ExecutionResult(
                output=output,
                status=ExecutionStatus.COMPLETE,
                tokens_used=tokens_used,
                runtime_name="openai_codex",
                session_id=context.session_id,
            )

        except asyncio.TimeoutError:
            logger.warning(f"OpenAI execution timed out after {self.timeout_seconds}s")
            return ExecutionResult(
                output="",
                status=ExecutionStatus.TIMEOUT,
                runtime_name="openai_codex",
                session_id=context.session_id,
                error_message=f"Execution timed out after {self.timeout_seconds} seconds",
                error_type="TimeoutError",
            )

        except Exception as e:
            logger.exception(f"OpenAI execution failed: {e}")
            return ExecutionResult(
                output="",
                status=ExecutionStatus.ERROR,
                runtime_name="openai_codex",
                session_id=context.session_id,
                error_message=str(e),
                error_type=type(e).__name__,
            )

        finally:
            self._current_session_id = None

    def _build_tools(self, context: ExecutionContext) -> List[Dict[str, Any]]:
        """Build tools list for OpenAI API.

        Args:
            context: Execution context

        Returns:
            List of tool definitions
        """
        tools = []

        # Add built-in tools
        if self.enable_code_interpreter:
            tools.append({"type": "code_interpreter"})

        if self.enable_file_search:
            tools.append({"type": "file_search"})

        # Add custom function tools (validated and normalized)
        if self.custom_tools:
            function_tools = OpenAIToolMapper.to_runtime_format(
                self.custom_tools,
                strict=False,
            )
            tools.extend(function_tools)

        # Add context-provided tools
        if context.tools:
            context_tools = OpenAIToolMapper.to_runtime_format(
                context.tools,
                strict=False,
            )
            tools.extend(context_tools)

        return tools

    def _build_input(self, context: ExecutionContext) -> str:
        """Build input content for API call.

        Args:
            context: Execution context

        Returns:
            Input string
        """
        # For Responses API, input is the task/prompt
        return context.task

    def _extract_output(self, response: Any) -> str:
        """Extract output text from response.

        Args:
            response: OpenAI API response

        Returns:
            Output text
        """
        # Handle different response structures
        if hasattr(response, "output"):
            # Responses API format
            output_items = response.output
            if isinstance(output_items, list):
                # Extract text from output items
                texts = []
                for item in output_items:
                    if hasattr(item, "text"):
                        texts.append(item.text)
                    elif hasattr(item, "content"):
                        texts.append(str(item.content))
                    elif isinstance(item, str):
                        texts.append(item)
                return "\n".join(texts)
            return str(output_items)

        if hasattr(response, "choices"):
            # Chat completion format
            if response.choices:
                message = response.choices[0].message
                if hasattr(message, "content") and message.content:
                    return message.content
                return ""

        # Fallback
        return str(response)

    def _extract_token_usage(self, response: Any) -> int:
        """Extract token usage from response.

        Args:
            response: OpenAI API response

        Returns:
            Total tokens used
        """
        if hasattr(response, "usage"):
            usage = response.usage
            if hasattr(usage, "total_tokens"):
                return usage.total_tokens
        return 0

    async def stream(
        self,
        context: ExecutionContext,
    ) -> AsyncIterator[str]:
        """Stream OpenAI response.

        Args:
            context: Execution context

        Yields:
            Output chunks
        """
        await self.ensure_initialized()

        self._current_session_id = context.session_id

        try:
            tools = self._build_tools(context)

            # Stream using Responses API
            stream = await self._client.responses.create(
                model=self.model,
                input=context.task,
                tools=tools if tools else None,
                temperature=self.temperature,
                max_output_tokens=self.max_completion_tokens,
                stream=True,
            )

            async for chunk in stream:
                if hasattr(chunk, "delta"):
                    delta = chunk.delta
                    if hasattr(delta, "text") and delta.text:
                        yield delta.text

        finally:
            self._current_session_id = None

    async def interrupt(
        self,
        session_id: str,
        mode: str = "graceful",
    ) -> bool:
        """Interrupt an ongoing execution.

        For OpenAI API, interruption is limited since requests are
        synchronous at the HTTP level.

        Args:
            session_id: Session to interrupt
            mode: Interrupt mode

        Returns:
            True if interrupt was successful
        """
        if self._current_session_id != session_id:
            return False

        # OpenAI API doesn't support true interruption
        # We can only cancel at the streaming level
        logger.warning(
            "OpenAI API does not support true interruption. "
            "Request will complete but result may be ignored."
        )
        return False

    def map_tools(
        self,
        kaizen_tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Map Kaizen tools to OpenAI format.

        Args:
            kaizen_tools: Tools to map

        Returns:
            Tools in OpenAI format
        """
        return OpenAIToolMapper.for_responses_api(
            kaizen_tools,
            enable_code_interpreter=self.enable_code_interpreter,
            enable_file_search=self.enable_file_search,
        )

    def normalize_result(
        self,
        raw_result: Any,
    ) -> ExecutionResult:
        """Normalize OpenAI result to ExecutionResult.

        Args:
            raw_result: Raw API response

        Returns:
            Normalized ExecutionResult
        """
        if isinstance(raw_result, ExecutionResult):
            return raw_result

        if isinstance(raw_result, str):
            return ExecutionResult.from_success(
                output=raw_result,
                runtime_name="openai_codex",
            )

        if isinstance(raw_result, dict):
            return ExecutionResult.from_dict(raw_result)

        return ExecutionResult.from_success(
            output=str(raw_result),
            runtime_name="openai_codex",
        )

    async def health_check(self) -> bool:
        """Check if OpenAI API is available.

        Returns:
            True if API is accessible
        """
        try:
            await self.ensure_initialized()
            # Simple models list to verify connectivity
            await self._client.models.list()
            return True
        except Exception as e:
            logger.warning(f"OpenAI health check failed: {e}")
            return False

    async def cleanup(self) -> None:
        """Clean up uploaded files."""
        if self._client and self._uploaded_files:
            for file_id in self._uploaded_files.values():
                try:
                    await self._client.files.delete(file_id)
                except Exception as e:
                    logger.warning(f"Failed to delete file {file_id}: {e}")

            self._uploaded_files.clear()

    def __repr__(self) -> str:
        return (
            f"OpenAICodexAdapter(model={self.model}, "
            f"code_interpreter={self.enable_code_interpreter})"
        )


# Convenience function
async def is_openai_available() -> bool:
    """Check if OpenAI API is available.

    Returns:
        True if OpenAI API is accessible
    """
    adapter = OpenAICodexAdapter()
    return await adapter.health_check()
