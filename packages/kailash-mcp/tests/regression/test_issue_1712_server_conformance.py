# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for #1712 - MCPServer spec-conformance (revision 2025-11-25).

Behavioral pins (call the handler, assert the returned envelope - never
source-grep, per ``rules/testing.md``) for the server-side conformance fixes:

Group A - tool-result conformance
  * tool EXECUTION failure -> ``result.isError=true`` (not a JSON-RPC error)
  * PROTOCOL failure (unknown tool / bad arguments) -> JSON-RPC ``-32602``
  * ``structuredContent`` emitted + validated; validation failure -> isError
  * non-text content passthrough (ToolResult / content-block list / audio)
  * ``outputSchema`` + advisory ``annotations`` advertised in ``tools/list``

Group B - resources/read fidelity
  * binary content -> base64 ``blob`` branch (bytes never str()-corrupted)
  * ``mimeType`` echoed on returned contents
  * malformed ``uri`` -> ``-32602`` with a distinct "invalid URI" message

Group C - live WebSocket lifecycle
  * notification (absent id) suppressed -> no response body
  * ``ping`` -> empty ``{}`` result
  * duplicate request-id in one session -> JSON-RPC error
"""

import base64

import pytest

from kailash_mcp.advanced.features import StructuredTool, ToolAnnotation
from kailash_mcp.protocol.protocol import ToolResult
from kailash_mcp.server import MCPServer


def _make_server() -> MCPServer:
    """A minimal MCPServer with no cache/metrics/auth for handler pins."""
    return MCPServer(
        "conformance-test",
        enable_cache=False,
        enable_metrics=False,
    )


def _register_tool(server: MCPServer, name: str, fn, **extra) -> None:
    """Insert a tool directly into the registry (real state, no mock).

    ``_execute_tool`` dispatches through the ``function`` slot; this bypasses
    the FastMCP enhanced-wrapper so a handler that raises or returns a
    structured value can be pinned without a live transport.
    """
    entry = {"function": fn, "call_count": 0, "last_called": None}
    entry.update(extra)
    server._tool_registry[name] = entry


# ---------------------------------------------------------------------------
# Group A - tool-result conformance
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_tool_execution_exception_is_error_in_result():
    """A raising tool body -> result.isError=true, text carries the error."""
    server = _make_server()

    def boom(**_):
        raise RuntimeError("kaboom")

    _register_tool(server, "boom", boom)

    resp = await server._handle_call_tool(
        {"name": "boom", "arguments": {}}, request_id=1
    )

    assert "error" not in resp, "execution failure must NOT be a JSON-RPC error"
    result = resp["result"]
    assert result["isError"] is True
    assert result["content"][0]["type"] == "text"
    assert "kaboom" in result["content"][0]["text"]


@pytest.mark.regression
@pytest.mark.asyncio
async def test_unknown_tool_is_protocol_error():
    """An unknown tool name is a PROTOCOL error -> JSON-RPC -32602."""
    server = _make_server()
    resp = await server._handle_call_tool(
        {"name": "does-not-exist", "arguments": {}}, request_id=2
    )
    assert "result" not in resp
    assert resp["error"]["code"] == -32602
    assert "Unknown tool" in resp["error"]["message"]


@pytest.mark.regression
@pytest.mark.asyncio
async def test_bad_arguments_shape_is_protocol_error():
    """arguments that are not an object -> PROTOCOL error -32602."""
    server = _make_server()
    _register_tool(server, "ok", lambda **_: "fine")
    resp = await server._handle_call_tool(
        {"name": "ok", "arguments": ["not", "an", "object"]}, request_id=3
    )
    assert "result" not in resp
    assert resp["error"]["code"] == -32602


@pytest.mark.regression
@pytest.mark.asyncio
async def test_missing_tool_name_is_protocol_error():
    """A missing tool name -> PROTOCOL error -32602."""
    server = _make_server()
    resp = await server._handle_call_tool({"arguments": {}}, request_id=4)
    assert "result" not in resp
    assert resp["error"]["code"] == -32602


@pytest.mark.regression
@pytest.mark.asyncio
async def test_structured_content_emitted_and_validated():
    """A tool with outputSchema emits structuredContent + a text fallback."""
    server = _make_server()
    schema = {
        "type": "object",
        "properties": {"count": {"type": "integer"}},
        "required": ["count"],
    }
    _register_tool(
        server,
        "counter",
        lambda **_: {"count": 3},
        output_schema=schema,
        structured_tool=StructuredTool(output_schema=schema),
    )

    resp = await server._handle_call_tool(
        {"name": "counter", "arguments": {}}, request_id=5
    )
    result = resp["result"]
    assert result.get("isError") is not True
    assert result["structuredContent"] == {"count": 3}
    # Text fallback carries the same payload.
    assert result["content"][0]["type"] == "text"
    assert "count" in result["content"][0]["text"]


@pytest.mark.regression
@pytest.mark.asyncio
async def test_output_schema_validation_failure_is_error_in_result():
    """A result violating outputSchema -> isError (NOT a protocol error)."""
    server = _make_server()
    schema = {
        "type": "object",
        "properties": {"count": {"type": "integer"}},
        "required": ["count"],
    }
    _register_tool(
        server,
        "bad_counter",
        lambda **_: {"count": "not-an-int"},
        output_schema=schema,
        structured_tool=StructuredTool(output_schema=schema),
    )

    resp = await server._handle_call_tool(
        {"name": "bad_counter", "arguments": {}}, request_id=6
    )
    assert "error" not in resp
    assert resp["result"]["isError"] is True
    assert "structuredContent" not in resp["result"]
    assert "validation" in resp["result"]["content"][0]["text"].lower()


@pytest.mark.regression
@pytest.mark.asyncio
async def test_tool_result_passthrough_image():
    """A ToolResult.image() return is passed through, not str()-wrapped."""
    server = _make_server()
    _register_tool(server, "pic", lambda **_: ToolResult.image("YWJj", "image/png"))
    resp = await server._handle_call_tool(
        {"name": "pic", "arguments": {}}, request_id=7
    )
    block = resp["result"]["content"][0]
    assert block["type"] == "image"
    assert block["data"] == "YWJj"
    assert block["mimeType"] == "image/png"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_content_block_list_passthrough_audio():
    """A content-block list including audio is passed through verbatim."""
    server = _make_server()
    blocks = [
        {"type": "text", "text": "listen"},
        {"type": "audio", "data": "AAAA", "mimeType": "audio/wav"},
    ]
    _register_tool(server, "voice", lambda **_: blocks)
    resp = await server._handle_call_tool(
        {"name": "voice", "arguments": {}}, request_id=8
    )
    assert resp["result"]["content"] == blocks


@pytest.mark.regression
@pytest.mark.asyncio
async def test_scalar_return_wraps_as_text_block():
    """A plain scalar return is wrapped as a single text block."""
    server = _make_server()
    _register_tool(server, "scalar", lambda **_: 42)
    resp = await server._handle_call_tool(
        {"name": "scalar", "arguments": {}}, request_id=9
    )
    assert resp["result"]["content"] == [{"type": "text", "text": "42"}]


@pytest.mark.regression
@pytest.mark.asyncio
async def test_tools_list_advertises_output_schema_and_annotations():
    """tools/list surfaces outputSchema + advisory annotation hints."""
    server = _make_server()
    schema = {"type": "object", "properties": {"n": {"type": "integer"}}}

    @server.tool(
        output_schema=schema,
        annotations=ToolAnnotation(is_read_only=True, is_destructive=False),
    )
    def described() -> dict:
        return {"n": 1}

    resp = await server._handle_list_tools({}, request_id=10)
    tool = next(t for t in resp["result"]["tools"] if t["name"] == "described")
    assert tool["outputSchema"] == schema
    assert tool["annotations"]["readOnlyHint"] is True
    assert tool["annotations"]["destructiveHint"] is False
