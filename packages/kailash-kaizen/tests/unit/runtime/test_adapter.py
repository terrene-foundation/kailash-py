"""
Unit Tests for Runtime Adapter (Tier 1)

Tests RuntimeAdapter ABC and BaseRuntimeAdapter default implementations.

Coverage:
- Abstract interface validation
- Default implementations in BaseRuntimeAdapter
- stream() method (default and custom)
- interrupt() method
- map_tools() pass-through
- normalize_result() handling
- health_check(), warmup(), cleanup()
- get_native_tool_names(), supports_model()
"""

from typing import Any, AsyncIterator, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest

from kaizen.runtime.adapter import BaseRuntimeAdapter, ProgressCallback, RuntimeAdapter
from kaizen.runtime.capabilities import RuntimeCapabilities
from kaizen.runtime.context import ExecutionContext, ExecutionResult, ExecutionStatus


class ConcreteRuntimeAdapter(RuntimeAdapter):
    """Concrete implementation for testing RuntimeAdapter ABC."""

    def __init__(
        self,
        runtime_name: str = "test_runtime",
        supports_streaming: bool = True,
        supports_interrupt: bool = True,
        native_tools: Optional[List[str]] = None,
        supported_models: Optional[List[str]] = None,
    ):
        self._capabilities = RuntimeCapabilities(
            runtime_name=runtime_name,
            provider="test_provider",
            supports_streaming=supports_streaming,
            supports_interrupt=supports_interrupt,
            native_tools=native_tools or ["tool1", "tool2"],
            supported_models=supported_models or ["model-a", "model-b"],
        )
        self._execute_result: Optional[ExecutionResult] = None
        self._interrupt_result = True

    @property
    def capabilities(self) -> RuntimeCapabilities:
        return self._capabilities

    async def execute(
        self,
        context: ExecutionContext,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ExecutionResult:
        if self._execute_result:
            return self._execute_result
        return ExecutionResult.from_success(
            output=f"Executed: {context.task}",
            runtime_name=self._capabilities.runtime_name,
        )

    async def stream(self, context: ExecutionContext) -> AsyncIterator[str]:
        yield "chunk1"
        yield "chunk2"
        yield "chunk3"

    async def interrupt(self, session_id: str, mode: str = "graceful") -> bool:
        return self._interrupt_result

    def map_tools(self, kaizen_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Add a marker to show transformation happened
        return [{"transformed": True, **tool} for tool in kaizen_tools]

    def normalize_result(self, raw_result: Any) -> ExecutionResult:
        if isinstance(raw_result, ExecutionResult):
            return raw_result
        return ExecutionResult.from_success(
            output=str(raw_result),
            runtime_name=self._capabilities.runtime_name,
        )


class ConcreteBaseAdapter(BaseRuntimeAdapter):
    """Concrete implementation extending BaseRuntimeAdapter."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        runtime_name: str = "base_test",
        supports_streaming: bool = False,
        supports_interrupt: bool = False,
    ):
        super().__init__(config)
        self._capabilities = RuntimeCapabilities(
            runtime_name=runtime_name,
            provider="test",
            supports_streaming=supports_streaming,
            supports_interrupt=supports_interrupt,
            native_tools=["read_file", "write_file"],
            supported_models=["test-model"],
        )

    @property
    def capabilities(self) -> RuntimeCapabilities:
        return self._capabilities

    async def execute(
        self,
        context: ExecutionContext,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ExecutionResult:
        await self.ensure_initialized()
        return ExecutionResult.from_success(
            output=f"Base executed: {context.task}",
            runtime_name=self._capabilities.runtime_name,
        )


class TestRuntimeAdapter:
    """Test RuntimeAdapter abstract base class."""

    def test_cannot_instantiate_abstract_class(self):
        """Test that RuntimeAdapter cannot be instantiated directly."""
        with pytest.raises(TypeError):
            RuntimeAdapter()

    def test_concrete_implementation(self):
        """Test that concrete implementation works."""
        adapter = ConcreteRuntimeAdapter()
        assert adapter.capabilities.runtime_name == "test_runtime"

    def test_capabilities_property(self):
        """Test capabilities property returns RuntimeCapabilities."""
        adapter = ConcreteRuntimeAdapter(
            runtime_name="my_runtime",
            native_tools=["bash", "read"],
        )
        caps = adapter.capabilities

        assert isinstance(caps, RuntimeCapabilities)
        assert caps.runtime_name == "my_runtime"
        assert "bash" in caps.native_tools

    @pytest.mark.asyncio
    async def test_execute_method(self):
        """Test execute method."""
        adapter = ConcreteRuntimeAdapter()
        context = ExecutionContext(task="Test task")

        result = await adapter.execute(context)

        assert isinstance(result, ExecutionResult)
        assert result.is_success
        assert "Test task" in result.output

    @pytest.mark.asyncio
    async def test_execute_with_progress(self):
        """Test execute method with progress callback."""
        adapter = ConcreteRuntimeAdapter()
        context = ExecutionContext(task="Test task")
        progress_calls = []

        def on_progress(event_type: str, data: Dict[str, Any]):
            progress_calls.append((event_type, data))

        result = await adapter.execute(context, on_progress=on_progress)

        assert result.is_success

    @pytest.mark.asyncio
    async def test_stream_method(self):
        """Test stream method yields chunks."""
        adapter = ConcreteRuntimeAdapter()
        context = ExecutionContext(task="Stream test")

        chunks = []
        async for chunk in adapter.stream(context):
            chunks.append(chunk)

        assert chunks == ["chunk1", "chunk2", "chunk3"]

    @pytest.mark.asyncio
    async def test_interrupt_method(self):
        """Test interrupt method."""
        adapter = ConcreteRuntimeAdapter()

        result = await adapter.interrupt("session-123", mode="graceful")
        assert result is True

        result = await adapter.interrupt("session-456", mode="immediate")
        assert result is True

    def test_map_tools_method(self):
        """Test map_tools transforms tools."""
        adapter = ConcreteRuntimeAdapter()
        tools = [
            {"name": "read_file", "type": "function"},
            {"name": "write_file", "type": "function"},
        ]

        mapped = adapter.map_tools(tools)

        assert len(mapped) == 2
        assert all(t.get("transformed") for t in mapped)

    def test_normalize_result_method(self):
        """Test normalize_result converts to ExecutionResult."""
        adapter = ConcreteRuntimeAdapter()

        # String input
        result = adapter.normalize_result("raw output")
        assert isinstance(result, ExecutionResult)
        assert result.output == "raw output"

        # ExecutionResult passthrough
        existing = ExecutionResult.from_success("existing", "test")
        result = adapter.normalize_result(existing)
        assert result is existing


class TestRuntimeAdapterHelperMethods:
    """Test helper methods with default implementations."""

    @pytest.mark.asyncio
    async def test_health_check_default(self):
        """Test health_check returns True by default."""
        adapter = ConcreteRuntimeAdapter()
        result = await adapter.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_warmup_default(self):
        """Test warmup completes without error."""
        adapter = ConcreteRuntimeAdapter()
        await adapter.warmup()  # Should not raise

    @pytest.mark.asyncio
    async def test_cleanup_default(self):
        """Test cleanup completes without error."""
        adapter = ConcreteRuntimeAdapter()
        await adapter.cleanup()  # Should not raise

    def test_get_native_tool_names(self):
        """Test get_native_tool_names returns tools from capabilities."""
        adapter = ConcreteRuntimeAdapter(native_tools=["bash", "read", "write"])

        tools = adapter.get_native_tool_names()

        assert tools == ["bash", "read", "write"]

    def test_supports_model_true(self):
        """Test supports_model returns True for supported model."""
        adapter = ConcreteRuntimeAdapter(supported_models=["gpt-4", "claude-3"])

        assert adapter.supports_model("gpt-4") is True
        assert adapter.supports_model("claude-3") is True

    def test_supports_model_false(self):
        """Test supports_model returns False for unsupported model."""
        adapter = ConcreteRuntimeAdapter(supported_models=["gpt-4"])

        assert adapter.supports_model("unknown-model") is False

    def test_repr(self):
        """Test string representation."""
        adapter = ConcreteRuntimeAdapter(runtime_name="my_test_runtime")

        repr_str = repr(adapter)

        assert "ConcreteRuntimeAdapter" in repr_str
        assert "my_test_runtime" in repr_str


class TestBaseRuntimeAdapter:
    """Test BaseRuntimeAdapter with default implementations."""

    def test_init_with_config(self):
        """Test initialization with config."""
        config = {"key": "value", "timeout": 30}
        adapter = ConcreteBaseAdapter(config=config)

        assert adapter.config == config
        assert adapter._is_initialized is False

    def test_init_without_config(self):
        """Test initialization without config."""
        adapter = ConcreteBaseAdapter()

        assert adapter.config == {}
        assert adapter._is_initialized is False

    @pytest.mark.asyncio
    async def test_ensure_initialized(self):
        """Test ensure_initialized calls warmup once."""
        adapter = ConcreteBaseAdapter()

        assert adapter._is_initialized is False

        await adapter.ensure_initialized()
        assert adapter._is_initialized is True

        # Second call should not re-warmup
        await adapter.ensure_initialized()
        assert adapter._is_initialized is True

    @pytest.mark.asyncio
    async def test_execute_calls_ensure_initialized(self):
        """Test execute calls ensure_initialized."""
        adapter = ConcreteBaseAdapter()
        context = ExecutionContext(task="Test")

        assert adapter._is_initialized is False

        result = await adapter.execute(context)

        assert adapter._is_initialized is True
        assert result.is_success


class TestBaseRuntimeAdapterStream:
    """Test BaseRuntimeAdapter stream implementation."""

    @pytest.mark.asyncio
    async def test_stream_when_supported(self):
        """Test stream yields execute result when streaming supported."""
        adapter = ConcreteBaseAdapter(
            supports_streaming=True,
            runtime_name="streaming_runtime",
        )
        context = ExecutionContext(task="Stream test")

        chunks = []
        async for chunk in adapter.stream(context):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert "Stream test" in chunks[0]

    @pytest.mark.asyncio
    async def test_stream_when_not_supported(self):
        """Test stream raises when streaming not supported."""
        adapter = ConcreteBaseAdapter(
            supports_streaming=False,
            runtime_name="no_stream",
        )
        context = ExecutionContext(task="Test")

        with pytest.raises(NotImplementedError) as exc_info:
            async for _ in adapter.stream(context):
                pass

        assert "no_stream" in str(exc_info.value)
        assert "not support streaming" in str(exc_info.value)


class TestBaseRuntimeAdapterInterrupt:
    """Test BaseRuntimeAdapter interrupt implementation."""

    @pytest.mark.asyncio
    async def test_interrupt_when_not_supported(self):
        """Test interrupt returns False when not supported."""
        adapter = ConcreteBaseAdapter(supports_interrupt=False)

        result = await adapter.interrupt("session-1")

        assert result is False

    @pytest.mark.asyncio
    async def test_interrupt_when_supported_default(self):
        """Test interrupt returns False by default even when supported."""
        # BaseRuntimeAdapter requires subclass to implement actual logic
        adapter = ConcreteBaseAdapter(supports_interrupt=True)

        result = await adapter.interrupt("session-1")

        assert result is False


class TestBaseRuntimeAdapterMapTools:
    """Test BaseRuntimeAdapter map_tools implementation."""

    def test_map_tools_passthrough(self):
        """Test default map_tools passes tools through unchanged."""
        adapter = ConcreteBaseAdapter()
        tools = [
            {"type": "function", "function": {"name": "tool1"}},
            {"type": "function", "function": {"name": "tool2"}},
        ]

        mapped = adapter.map_tools(tools)

        assert mapped == tools

    def test_map_tools_empty_list(self):
        """Test map_tools handles empty list."""
        adapter = ConcreteBaseAdapter()

        mapped = adapter.map_tools([])

        assert mapped == []


class TestBaseRuntimeAdapterNormalizeResult:
    """Test BaseRuntimeAdapter normalize_result implementation."""

    def test_normalize_execution_result(self):
        """Test normalize_result passes through ExecutionResult."""
        adapter = ConcreteBaseAdapter()
        original = ExecutionResult.from_success("original", "test")

        result = adapter.normalize_result(original)

        assert result is original

    def test_normalize_string(self):
        """Test normalize_result handles string."""
        adapter = ConcreteBaseAdapter(runtime_name="my_runtime")

        result = adapter.normalize_result("string output")

        assert isinstance(result, ExecutionResult)
        assert result.is_success
        assert result.output == "string output"
        assert result.runtime_name == "my_runtime"

    def test_normalize_dict(self):
        """Test normalize_result handles dict via from_dict."""
        adapter = ConcreteBaseAdapter()
        data = {
            "output": "dict output",
            "status": "complete",
            "tokens_used": 100,
        }

        result = adapter.normalize_result(data)

        assert isinstance(result, ExecutionResult)
        assert result.output == "dict output"
        assert result.status == ExecutionStatus.COMPLETE

    def test_normalize_other_type(self):
        """Test normalize_result handles arbitrary types via str()."""
        adapter = ConcreteBaseAdapter(runtime_name="test")

        result = adapter.normalize_result(12345)

        assert isinstance(result, ExecutionResult)
        assert result.output == "12345"

        result = adapter.normalize_result(["item1", "item2"])
        assert result.output == "['item1', 'item2']"


class TestProgressCallback:
    """Test ProgressCallback type alias."""

    def test_progress_callback_signature(self):
        """Test progress callback has correct signature."""
        calls = []

        def my_callback(event_type: str, data: Dict[str, Any]) -> None:
            calls.append((event_type, data))

        # Should be valid as ProgressCallback
        callback: ProgressCallback = my_callback

        callback("tool_call", {"tool": "read_file"})
        callback("output", {"text": "result"})

        assert len(calls) == 2
        assert calls[0] == ("tool_call", {"tool": "read_file"})
        assert calls[1] == ("output", {"text": "result"})
