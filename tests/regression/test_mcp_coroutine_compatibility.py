"""Coroutine dispatch retains supported markers without deprecated predicates."""

import asyncio
import functools
import inspect
import warnings

import pytest

from kailash_mcp._async_compat import is_coroutine_function
from kailash_mcp.advanced.features import StructuredTool
from kailash_mcp.auth.providers import APIKeyAuth
from kailash_mcp.errors import MCPError, ToolError, wrap_with_error_handling
from kailash_mcp.server import MCPServer
from kailash_mcp.utils.cache import CacheManager
from kailash_mcp.utils.metrics import MetricsCollector


def legacy_mark(function):
    function._is_coroutine = asyncio.coroutines._is_coroutine
    return function


def test_detector_preserves_callable_classification_without_invoking():
    calls = []

    async def native(value=None):
        calls.append(value)

    def sync():
        calls.append("sync")

    class Callable:
        async def __call__(self):
            calls.append("instance")

        async def bound(self):
            calls.append("bound")

    @functools.wraps(native)
    def wrapped_only():
        return native()

    def marked():
        return native()

    legacy_mark(marked)

    @functools.wraps(marked)
    def wrapped_marker():
        return marked()

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        for function in (
            native,
            functools.partial(native, 1),
            Callable().bound,
            marked,
            wrapped_marker,
        ):
            assert is_coroutine_function(function) is True
        for function in (sync, Callable(), wrapped_only, functools.partial(marked)):
            assert is_coroutine_function(function) is False
    assert calls == []


def test_marker_is_identity_not_truthiness():
    class Marker:
        def __bool__(self):
            raise AssertionError("marker truthiness")

    def function():
        raise AssertionError("classification invoked function")

    function._is_coroutine = Marker()
    assert is_coroutine_function(function) is False


def test_inspect_marker_when_supported():
    marker = getattr(inspect, "markcoroutinefunction", None)
    if marker is None:
        assert not hasattr(inspect, "markcoroutinefunction")
        return

    def function():
        raise AssertionError("classification invoked function")

    assert is_coroutine_function(marker(function)) is True


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["native", "legacy", "sync"])
@pytest.mark.parametrize("surface", ["metrics", "cache", "errors", "structured"])
async def test_public_decorators_preserve_dispatch_and_single_execution(kind, surface):
    calls = []

    async def native(value):
        calls.append(value)
        return value + 1

    def sync(value):
        calls.append(value)
        return value + 1

    def factory(value):
        return native(value)

    function = (
        native
        if kind == "native"
        else legacy_mark(factory) if kind == "legacy" else sync
    )
    decorators = {
        "metrics": MetricsCollector().track_tool(),
        "cache": CacheManager().cached(),
        "errors": wrap_with_error_handling,
        "structured": StructuredTool(),
    }
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        wrapped = decorators[surface](function)
        value = wrapped(4)
        result = await value if inspect.isawaitable(value) else value
        assert result == 5
        if surface == "cache":
            value = wrapped(4)
            assert (await value if inspect.isawaitable(value) else value) == 5
    assert calls == [4]


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["metrics", "cache", "errors", "structured"])
async def test_marked_error_identity_is_preserved(surface):
    original = MCPError("controlled failure")
    calls = []

    async def fail():
        calls.append("body")
        raise original

    @legacy_mark
    def function():
        return fail()

    decorators = {
        "metrics": MetricsCollector().track_tool(),
        "cache": CacheManager().cached(),
        "errors": wrap_with_error_handling,
        "structured": StructuredTool(),
    }
    with pytest.raises(MCPError) as caught:
        await decorators[surface](function)()
    assert caught.value is original
    assert calls == ["body"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["native", "legacy", "sync"])
async def test_server_authentication_precedes_cache_and_strips_credentials(kind):
    calls = []

    async def native(value: int) -> int:
        calls.append(value)
        return value + 1

    def sync(value: int) -> int:
        calls.append(value)
        return value + 1

    def factory(value: int) -> int:
        return native(value)

    function = (
        native
        if kind == "native"
        else legacy_mark(factory) if kind == "legacy" else sync
    )
    server = MCPServer(
        "coroutine-parity",
        enable_cache=True,
        enable_metrics=False,
        auth_provider=APIKeyAuth(keys={"test-key": {"permissions": ["read"]}}),
    )
    wrapped = server.tool(required_permission="read", cache_key="parity")(function)

    async def invoke(**kwargs):
        result = wrapped(**kwargs)
        return await result if inspect.isawaitable(result) else result

    with pytest.raises(ToolError):
        await invoke(value=4)
    assert calls == []
    assert await invoke(value=4, api_key="test-key") == 5
    assert await invoke(value=4, api_key="test-key") == 5
    assert calls == [4]
    with pytest.raises(ToolError):
        await invoke(value=4)
    assert calls == [4]
    assert server._active_sessions == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["native", "legacy", "sync"])
@pytest.mark.parametrize("surface", ["subscription", "protocol", "transport"])
async def test_callback_consumers_await_the_supported_function_once(kind, surface):
    from kailash_mcp.advanced.subscriptions import DataEnrichmentTransformer
    from kailash_mcp.protocol.protocol import ProgressManager
    from kailash_mcp.transports.transports import WebSocketServerTransport

    calls = []

    async def native(*args):
        calls.append(args)
        return {"result": "complete"}

    def sync(*args):
        calls.append(args)
        return {"result": "complete"}

    def factory(*args):
        return native(*args)

    function = (
        native
        if kind == "native"
        else legacy_mark(factory) if kind == "legacy" else sync
    )
    if surface == "subscription":
        result = await DataEnrichmentTransformer({"derived": function}).transform(
            {}, {}
        )
        assert result["derived"] == {"result": "complete"}
    elif surface == "protocol":
        manager = ProgressManager()
        token = manager.start_progress("operation")
        manager.add_progress_callback(token, function)
        await manager.update_progress(token, progress=1)
        assert calls[0][0].params["progress"] == 1
    else:
        transport = WebSocketServerTransport(message_handler=function)
        result = await transport._handle_message_safely({"id": 1}, "client")
        assert result == {"result": "complete"}
    assert len(calls) == 1
