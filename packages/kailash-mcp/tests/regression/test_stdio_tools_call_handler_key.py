"""Regression: the stdio ``tools/call`` branch read a registry key nothing writes.

``run_stdio``'s ``tools/call`` branch did::

    handler = self._tool_registry[tool_name]["handler"]

but the ``@server.tool()`` decorator writes ``"function"`` and
``"original_function"`` — never ``"handler"``. So EVERY decorator-registered
tool raised ``KeyError: 'handler'`` when invoked over stdio, surfaced to the
client as a ``-32603`` internal error.

``_execute_tool`` already resolved either shape (``"handler"`` or
``"function"``) AND enforced the ``disabled`` check. This stdio copy did
neither, so besides being broken it would have invoked a tool that
``disable_tool()`` had turned off — a check ``tools/call`` on every other
transport applies (``_handle_call_tool`` rejects a disabled tool with
``-32602``). Routing the branch through ``_execute_tool`` fixes both.
"""

import asyncio
import io
import json

import pytest
from kailash_mcp.server import MCPServer


def _server() -> MCPServer:
    server = MCPServer("regression-stdio-call")

    @server.tool()
    def echo(text: str) -> str:
        """Echo the input back."""
        return f"echoed:{text}"

    @server.tool()
    async def async_echo(text: str) -> str:
        """Echo the input back, asynchronously."""
        return f"async-echoed:{text}"

    return server


async def _drive_stdio(server: MCPServer, request: dict) -> dict:
    """Feed ONE request through the real ``run_stdio`` loop and read stdout."""
    import sys

    stdin = io.StringIO(json.dumps(request) + "\n")
    stdout = io.StringIO()
    real_stdin, real_stdout = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = stdin, stdout
    try:
        # readline() returns "" at EOF -> the loop breaks on its own.
        await asyncio.wait_for(server.run_stdio(), timeout=10)
    finally:
        sys.stdin, sys.stdout = real_stdin, real_stdout

    return json.loads(stdout.getvalue().strip().splitlines()[0])


@pytest.mark.regression
@pytest.mark.asyncio
async def test_stdio_call_invokes_decorator_registered_sync_tool():
    """A decorator-registered tool must be invocable over stdio."""
    server = _server()
    response = await _drive_stdio(
        server,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "echo", "arguments": {"text": "hi"}},
        },
    )

    assert "error" not in response, (
        "stdio tools/call failed on a decorator-registered tool; the branch "
        f"read a registry key the decorator never writes: {response!r}"
    )
    assert response["result"]["content"][0]["text"] == "echoed:hi", response


@pytest.mark.regression
@pytest.mark.asyncio
async def test_stdio_call_invokes_decorator_registered_async_tool():
    """An async tool must be awaited, not returned as a coroutine/Task repr."""
    server = _server()
    response = await _drive_stdio(
        server,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "async_echo", "arguments": {"text": "hi"}},
        },
    )

    assert "error" not in response, response
    assert response["result"]["content"][0]["text"] == "async-echoed:hi", (
        "an async tool's result was not awaited before serialisation: " f"{response!r}"
    )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_stdio_call_refuses_disabled_tool():
    """stdio must apply the disabled check every other transport applies."""
    server = _server()
    server.disable_tool("echo")

    response = await _drive_stdio(
        server,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "echo", "arguments": {"text": "hi"}},
        },
    )

    assert "error" in response, (
        "stdio tools/call invoked a tool that disable_tool() turned off: "
        f"{response!r}"
    )
    assert "disabled" in response["error"]["message"].lower(), response


@pytest.mark.regression
@pytest.mark.asyncio
async def test_stdio_call_still_reports_unknown_tool():
    """CONTROL: unknown-tool handling is unchanged by the routing fix."""
    server = _server()
    response = await _drive_stdio(
        server,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "nope", "arguments": {}},
        },
    )

    assert response["error"]["code"] == -32601, response
    assert "not found" in response["error"]["message"].lower(), response
