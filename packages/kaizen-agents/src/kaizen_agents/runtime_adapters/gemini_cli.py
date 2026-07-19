"""
GeminiCLIAdapter - Google Gemini API Integration

Delegates autonomous execution to Google's Gemini API, leveraging:
- Function Calling: Custom tool execution with typed declarations
- Code Execution: Gemini's native code execution capability
- Multi-modal: Vision and audio processing

This adapter provides a Kaizen-compatible interface to Gemini's
generative AI capabilities.

Usage:
    >>> from kaizen_agents.runtime_adapters.gemini_cli import GeminiCLIAdapter
    >>> from kaizen.runtime.context import ExecutionContext
    >>>
    >>> adapter = GeminiCLIAdapter(api_key="...")
    >>> context = ExecutionContext(task="Analyze this image")
    >>> result = await adapter.execute(context)
"""

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

from kaizen.runtime.adapter import BaseRuntimeAdapter, ProgressCallback
from kaizen.runtime.capabilities import RuntimeCapabilities
from kaizen.runtime.context import ExecutionContext, ExecutionResult, ExecutionStatus
from kaizen_agents.runtime_adapters.tool_mapping import GeminiToolMapper

logger = logging.getLogger(__name__)

# Provider-intrinsic default (this adapter IS Gemini). Documented module-level
# named constant, overridable via the KAIZEN_GEMINI_MODEL env var. NOT chained
# to the provider-agnostic default resolver — a non-Gemini model here is wrong.
_DEFAULT_MODEL = "gemini-1.5-pro"


class GeminiCLIAdapter(BaseRuntimeAdapter):
    """Adapter that delegates to Google Gemini API.

    Gemini API provides:
    - Function Calling: Typed function declarations with automatic invocation
    - Code Execution: Python code execution in sandboxed environment
    - Multi-modal: Image and audio understanding
    - Long context: Up to 1M tokens with Gemini 1.5

    This adapter wraps Gemini's capabilities in the RuntimeAdapter interface,
    enabling seamless integration with Kaizen's runtime selection.

    Key Features:
        - Native function calling with JSON Schema
        - Code execution tool for Python
        - Multi-modal input (images, audio, video)
        - Very long context window (1M tokens)
        - Competitive pricing

    Example:
        >>> adapter = GeminiCLIAdapter(
        ...     api_key=os.environ["GOOGLE_API_KEY"],
        ...     model="gemini-1.5-pro",
        ...     enable_code_execution=True,
        ... )
        >>>
        >>> context = ExecutionContext(task="Write and run a Python script")
        >>> result = await adapter.execute(context)
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        enable_code_execution: bool = False,
        custom_tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_output_tokens: int = 8192,
        timeout_seconds: float = 300,
        safety_settings: dict[str, str] | None = None,
        ungoverned: bool = False,
    ):
        """Initialize the GeminiCLIAdapter.

        Args:
            api_key: Google AI API key. If not provided, reads from
                    GOOGLE_API_KEY environment variable.
            model: Gemini model to use. Options:
                  - gemini-1.5-pro (1M context, best quality)
                  - gemini-1.5-flash (1M context, faster)
                  - gemini-1.0-pro (32K context)
            enable_code_execution: Enable Gemini's code execution tool.
            custom_tools: Custom function tools in Kaizen format.
            temperature: Sampling temperature (0.0-2.0).
            max_output_tokens: Maximum tokens in response.
            timeout_seconds: Execution timeout.
            safety_settings: Custom safety settings. Default allows most content.
            ungoverned: #1779 opt-out. When True, this adapter is exempt from the
                    governance_required posture gate. Default False (fail-closed).

        Raises:
            kailash.trust.pact.UngovernedEgressRefused: If the
                governance_required posture is active and this un-governed
                adapter would make real egress (unless ungoverned=True).
        """
        super().__init__()

        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        if model is None:
            model = os.environ.get("KAIZEN_GEMINI_MODEL", _DEFAULT_MODEL)
        self.model = model
        self.enable_code_execution = enable_code_execution
        self.custom_tools = custom_tools or []
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.timeout_seconds = timeout_seconds
        self.safety_settings = safety_settings
        self._ungoverned = ungoverned

        # #1779 governance_required posture: this adapter egresses DIRECTLY via
        # the google-genai SDK (the genai.Client built lazily in
        # ensure_initialized), NOT through the gated four-axis kaizen.llm.
        # LlmClient. Gate at construction, fail-closed and BEFORE the lazy
        # client is ever built: no mock path here (always a real client), so
        # is_mock=False; the only exemption is ungoverned=True (or posture OFF).
        from kaizen.llm.governance_gate import enforce_governance_posture

        enforce_governance_posture(
            is_mock=False,
            ungoverned=ungoverned,
            surface="kaizen_agents.GeminiCliAdapter",
        )

        # Gemini client (lazily initialized)
        self._client: Any | None = None
        self._types: Any | None = None

        # Session tracking
        self._current_session_id: str | None = None
        self._chat_session: Any | None = None

        # Build capabilities
        self._capabilities = self._build_capabilities()

    @property
    def capabilities(self) -> RuntimeCapabilities:
        """Return Gemini capabilities."""
        return self._capabilities

    def _build_capabilities(self) -> RuntimeCapabilities:
        """Build capabilities description."""
        native_tools = []
        if self.enable_code_execution:
            native_tools.append("code_execution")

        # Context size depends on model
        if "1.5" in self.model:
            max_context = 1000000  # 1M tokens
        else:
            max_context = 32000

        return RuntimeCapabilities(
            runtime_name="gemini_cli",
            provider="google",
            version="1.5.0",
            supports_streaming=True,
            supports_tool_calling=True,
            supports_parallel_tools=True,  # Gemini supports parallel function calls
            supports_vision=True,  # Native multi-modal
            supports_audio=True,  # Gemini 1.5+ supports audio
            supports_code_execution=self.enable_code_execution,
            supports_file_access=False,  # No direct file system access
            supports_web_access=False,  # Sandboxed
            supports_interrupt=True,
            max_context_tokens=max_context,
            max_output_tokens=self.max_output_tokens,
            cost_per_1k_input_tokens=0.35,  # Gemini 1.5 Pro pricing
            cost_per_1k_output_tokens=1.05,
            typical_latency_ms=800,
            native_tools=native_tools,
            supported_models=[
                "gemini-1.5-pro",
                "gemini-1.5-flash",
                "gemini-1.0-pro",
                "gemini-2.0-flash-exp",
            ],
            metadata={
                "code_execution": self.enable_code_execution,
                "multimodal": True,
            },
        )

    async def ensure_initialized(self) -> None:
        """Ensure Gemini client is initialized."""
        if self._client is None:
            try:
                from google import genai
                from google.genai import types as genai_types
            except ImportError:
                raise ImportError(
                    "The google-genai package is required for the Gemini runtime. "
                    "Install with: pip install google-genai"
                ) from None

            self._client = genai.Client(api_key=self.api_key)
            self._types = genai_types

        await super().ensure_initialized()

    def _get_safety_settings(self) -> list[dict[str, Any]] | None:
        """Get safety settings configuration.

        Returns:
            Safety settings or None for defaults
        """
        if self.safety_settings:
            return self.safety_settings

        # Default: allow most content for development
        # Production should use stricter settings
        return None

    def _build_generate_config(self, tools: list[Any] | None = None) -> Any:
        """Build a ``google.genai`` GenerateContentConfig for one request.

        Carries temperature + max_output_tokens, plus optional safety settings
        and tools. ``self._types`` is populated by ``ensure_initialized`` (the
        ``google.genai`` SDK moved per-request generation knobs out of the
        model object and into the config passed to each ``generate_content``).
        """
        config_kwargs: dict[str, Any] = {
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
        }
        safety = self._get_safety_settings()
        if safety:
            config_kwargs["safety_settings"] = safety
        if tools:
            config_kwargs["tools"] = tools
        return self._types.GenerateContentConfig(**config_kwargs)

    async def execute(
        self,
        context: ExecutionContext,
        on_progress: ProgressCallback | None = None,
    ) -> ExecutionResult:
        """Execute a task using Gemini API.

        Uses Gemini's generate_content with optional function calling.

        Args:
            context: Execution context with task and optional tools
            on_progress: Progress callback

        Returns:
            ExecutionResult with output and metrics
        """
        await self.ensure_initialized()

        self._current_session_id = context.session_id

        if on_progress:
            on_progress("starting", {"task": context.task[:100]})

        try:
            # Build tools configuration
            tools = self._build_tools(context)

            logger.info(
                f"Executing Gemini: {context.task[:50]}..., model: {self.model}"
            )

            if on_progress:
                on_progress("calling_api", {"model": self.model})

            # Generate content (tools, if any, are folded into the request
            # config — google.genai passes generation knobs per-call).
            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=self.model,
                contents=context.task,
                config=self._build_generate_config(tools),
            )

            # Extract output and handle function calls
            output = self._extract_output(response)
            tokens_used = self._extract_token_usage(response)

            if on_progress:
                on_progress("complete", {"output_length": len(output)})

            return ExecutionResult(
                output=output,
                status=ExecutionStatus.COMPLETE,
                tokens_used=tokens_used,
                runtime_name="gemini_cli",
                session_id=context.session_id,
            )

        except TimeoutError:
            logger.warning(f"Gemini execution timed out after {self.timeout_seconds}s")
            return ExecutionResult(
                output="",
                status=ExecutionStatus.TIMEOUT,
                runtime_name="gemini_cli",
                session_id=context.session_id,
                error_message=f"Execution timed out after {self.timeout_seconds} seconds",
                error_type="TimeoutError",
            )

        except Exception as e:
            logger.exception(f"Gemini execution failed: {e}")
            return ExecutionResult(
                output="",
                status=ExecutionStatus.ERROR,
                runtime_name="gemini_cli",
                session_id=context.session_id,
                error_message=str(e),
                error_type=type(e).__name__,
            )

        finally:
            self._current_session_id = None

    def _build_tools(self, context: ExecutionContext) -> list[Any] | None:
        """Build tools configuration for Gemini API.

        Args:
            context: Execution context

        Returns:
            Tools configuration or None
        """
        all_tools = []

        # Add code execution if enabled
        if self.enable_code_execution:
            # Gemini uses a special tool type for code execution
            try:
                from google.genai import types

                all_tools.append(types.Tool(code_execution=types.ToolCodeExecution()))
            except (ImportError, AttributeError):
                logger.warning("Code execution tool not available in this version")

        # Add custom function tools
        function_declarations = []

        if self.custom_tools:
            converted = GeminiToolMapper.to_gemini_format(self.custom_tools)
            function_declarations.extend(converted)

        if context.tools:
            converted = GeminiToolMapper.to_gemini_format(context.tools)
            function_declarations.extend(converted)

        # Add function declarations as a tool
        if function_declarations:
            try:
                from google.genai import types

                all_tools.append(
                    types.Tool(function_declarations=function_declarations)
                )
            except (ImportError, AttributeError):
                # Fallback: a plain dict is coerced by GenerateContentConfig.
                all_tools.append({"function_declarations": function_declarations})

        return all_tools if all_tools else None

    def _extract_output(self, response: Any) -> str:
        """Extract output text from Gemini response.

        Handles both text and function call responses.

        Args:
            response: Gemini API response

        Returns:
            Output text
        """
        if hasattr(response, "text"):
            return response.text

        # Handle candidates structure
        if hasattr(response, "candidates") and response.candidates:
            candidate = response.candidates[0]

            if hasattr(candidate, "content") and candidate.content:
                content = candidate.content

                if hasattr(content, "parts"):
                    parts = []
                    for part in content.parts:
                        if hasattr(part, "text") and part.text:
                            parts.append(part.text)
                        elif hasattr(part, "function_call"):
                            # Format function call for output
                            fc = part.function_call
                            parts.append(f"[Function Call: {fc.name}({fc.args})]")
                        elif hasattr(part, "executable_code"):
                            # Code execution result
                            code = part.executable_code
                            parts.append(f"```python\n{code.code}\n```")
                        elif hasattr(part, "code_execution_result"):
                            result = part.code_execution_result
                            parts.append(f"Output: {result.output}")

                    return "\n".join(parts)

        return str(response)

    def _extract_token_usage(self, response: Any) -> int:
        """Extract token usage from response.

        Args:
            response: Gemini API response

        Returns:
            Total tokens used
        """
        if hasattr(response, "usage_metadata"):
            usage = response.usage_metadata
            if hasattr(usage, "total_token_count"):
                return usage.total_token_count
        return 0

    async def stream(
        self,
        context: ExecutionContext,
    ) -> AsyncIterator[str]:
        """Stream Gemini response.

        Args:
            context: Execution context

        Yields:
            Output chunks
        """
        await self.ensure_initialized()

        self._current_session_id = context.session_id

        try:
            tools = self._build_tools(context)

            # Generate with streaming via the async client.
            response = await self._client.aio.models.generate_content_stream(
                model=self.model,
                contents=context.task,
                config=self._build_generate_config(tools),
            )

            async for chunk in response:
                if getattr(chunk, "text", None):
                    yield chunk.text
                elif getattr(chunk, "candidates", None):
                    for candidate in chunk.candidates:
                        content = getattr(candidate, "content", None)
                        if content and getattr(content, "parts", None):
                            for part in content.parts:
                                if getattr(part, "text", None):
                                    yield part.text

        finally:
            self._current_session_id = None

    async def interrupt(
        self,
        session_id: str,
        mode: str = "graceful",
    ) -> bool:
        """Interrupt an ongoing execution.

        Args:
            session_id: Session to interrupt
            mode: Interrupt mode

        Returns:
            True if interrupt was successful
        """
        if self._current_session_id != session_id:
            return False

        # Gemini API doesn't support true interruption
        logger.warning(
            "Gemini API does not support true interruption. "
            "Request will complete but result may be ignored."
        )
        return False

    def map_tools(
        self,
        kaizen_tools: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Map Kaizen tools to Gemini format.

        Args:
            kaizen_tools: Tools to map

        Returns:
            Tools in Gemini format
        """
        return GeminiToolMapper.to_gemini_format(kaizen_tools)

    def normalize_result(
        self,
        raw_result: Any,
    ) -> ExecutionResult:
        """Normalize Gemini result to ExecutionResult.

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
                runtime_name="gemini_cli",
            )

        if isinstance(raw_result, dict):
            return ExecutionResult.from_dict(raw_result)

        return ExecutionResult.from_success(
            output=str(raw_result),
            runtime_name="gemini_cli",
        )

    async def health_check(self) -> bool:
        """Check if Gemini API is available.

        Returns:
            True if API is accessible
        """
        try:
            await self.ensure_initialized()
            # Simple generation to verify connectivity
            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=self.model,
                contents="Hello",
                config=self._build_generate_config(None),
            )
            return response is not None
        except Exception as e:
            logger.warning(f"Gemini health check failed: {e}")
            return False

    def __repr__(self) -> str:
        return (
            f"GeminiCLIAdapter(model={self.model}, "
            f"code_execution={self.enable_code_execution})"
        )


# Convenience function
async def is_gemini_available() -> bool:
    """Check if Gemini API is available.

    Returns:
        True if Gemini API is accessible
    """
    adapter = GeminiCLIAdapter()
    return await adapter.health_check()
