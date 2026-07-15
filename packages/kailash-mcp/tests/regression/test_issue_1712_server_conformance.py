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


# ---------------------------------------------------------------------------
# Group B - resources/read fidelity
# ---------------------------------------------------------------------------


def _register_resource(
    server: MCPServer, uri: str, content, mime_type: str = "text/plain"
) -> None:
    """Insert a resource directly into the registry (real state, no mock)."""
    server._resource_registry[uri] = {
        "handler": lambda: content,
        "original_handler": None,
        "name": uri,
        "description": f"Resource: {uri}",
        "mime_type": mime_type,
        "created_at": 0.0,
    }


@pytest.mark.regression
@pytest.mark.asyncio
async def test_resource_read_bytes_emitted_as_base64_blob():
    """Raw bytes are base64 blob-encoded, never str()-corrupted into text."""
    server = _make_server()
    raw = bytes([0x00, 0x01, 0xFF, 0xFE, 0x80])
    _register_resource(server, "file://icon", raw, mime_type="application/octet-stream")

    resp = await server._handle_read_resource({"uri": "file://icon"}, request_id=20)
    item = resp["result"]["contents"][0]
    assert "text" not in item, "binary content MUST NOT use the text field"
    assert item["mimeType"] == "application/octet-stream"
    assert base64.b64decode(item["blob"]) == raw


@pytest.mark.regression
@pytest.mark.asyncio
async def test_resource_read_non_text_mime_uses_blob_branch():
    """A non-text mimeType routes str content through the blob branch."""
    server = _make_server()
    _register_resource(server, "img://logo", "PNGDATA", mime_type="image/png")

    resp = await server._handle_read_resource({"uri": "img://logo"}, request_id=21)
    item = resp["result"]["contents"][0]
    assert "text" not in item
    assert item["mimeType"] == "image/png"
    assert base64.b64decode(item["blob"]) == b"PNGDATA"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_resource_read_text_includes_mime_type():
    """Text content keeps the text field and echoes the registered mimeType."""
    server = _make_server()
    _register_resource(server, "data://note", "hello world", mime_type="text/markdown")

    resp = await server._handle_read_resource({"uri": "data://note"}, request_id=22)
    item = resp["result"]["contents"][0]
    assert item["text"] == "hello world"
    assert item["mimeType"] == "text/markdown"
    assert "blob" not in item


@pytest.mark.regression
@pytest.mark.asyncio
async def test_resource_read_json_mime_stays_text():
    """A structured application/json mimeType is treated as text, not blob."""
    server = _make_server()
    _register_resource(server, "data://cfg", '{"a": 1}', mime_type="application/json")
    resp = await server._handle_read_resource({"uri": "data://cfg"}, request_id=23)
    item = resp["result"]["contents"][0]
    assert item["text"] == '{"a": 1}'
    assert "blob" not in item


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("bad_uri", ["not a uri", "no-scheme-here", "", "  "])
async def test_resource_read_invalid_uri_is_distinct_error(bad_uri):
    """A malformed URI -> -32602 with a distinct 'Invalid URI' message."""
    server = _make_server()
    resp = await server._handle_read_resource({"uri": bad_uri}, request_id=24)
    assert "result" not in resp
    assert resp["error"]["code"] == -32602
    assert "Invalid URI" in resp["error"]["message"]


@pytest.mark.regression
@pytest.mark.asyncio
async def test_resource_read_valid_but_missing_is_not_found():
    """A well-formed but unregistered URI -> not-found (distinct from invalid)."""
    server = _make_server()
    resp = await server._handle_read_resource({"uri": "data://absent"}, request_id=25)
    assert resp["error"]["code"] == -32602
    assert "not found" in resp["error"]["message"].lower()


# ---------------------------------------------------------------------------
# Group C - live WebSocket lifecycle
# ---------------------------------------------------------------------------


def _ws_msg(method=None, request_id=None, **extra):
    msg = {"jsonrpc": "2.0", "params": {}}
    if method is not None:
        msg["method"] = method
    if request_id is not None:
        msg["id"] = request_id
    msg.update(extra)
    return msg


@pytest.mark.regression
@pytest.mark.asyncio
async def test_ws_notification_known_method_sends_nothing():
    """A notification (absent id) runs side-effects but returns no body."""
    server = _make_server()
    resp = await server._handle_websocket_message(
        _ws_msg(method="tools/list"), "client-a"
    )
    assert resp is None


@pytest.mark.regression
@pytest.mark.asyncio
async def test_ws_notification_unknown_method_sends_nothing():
    """A notification for an unknown method sends NOTHING, not a -32601 body."""
    server = _make_server()
    resp = await server._handle_websocket_message(
        _ws_msg(method="notifications/somethingUnknown"), "client-a"
    )
    assert resp is None


@pytest.mark.regression
@pytest.mark.asyncio
async def test_ws_ping_request_returns_empty_result():
    """A request-form ping returns an empty {} result."""
    server = _make_server()
    resp = await server._handle_websocket_message(
        _ws_msg(method="ping", request_id=100), "client-a"
    )
    assert resp["result"] == {}
    assert resp["id"] == 100
    assert "error" not in resp


@pytest.mark.regression
@pytest.mark.asyncio
async def test_ws_ping_notification_sends_nothing():
    """A notification-form ping (no id) sends no response."""
    server = _make_server()
    resp = await server._handle_websocket_message(_ws_msg(method="ping"), "client-a")
    assert resp is None


@pytest.mark.regression
@pytest.mark.asyncio
async def test_ws_duplicate_request_id_rejected_per_session():
    """A reused request id in one session -> Invalid Request (-32600)."""
    server = _make_server()

    first = await server._handle_websocket_message(
        _ws_msg(method="tools/list", request_id=7), "client-a"
    )
    assert "result" in first

    dup = await server._handle_websocket_message(
        _ws_msg(method="tools/list", request_id=7), "client-a"
    )
    assert "result" not in dup
    assert dup["error"]["code"] == -32600
    assert dup["id"] == 7


@pytest.mark.regression
@pytest.mark.asyncio
async def test_ws_request_id_reuse_scoped_per_session():
    """The same id is allowed under a DIFFERENT client session."""
    server = _make_server()
    await server._handle_websocket_message(
        _ws_msg(method="tools/list", request_id=7), "client-a"
    )
    # Same id, different session -> accepted.
    other = await server._handle_websocket_message(
        _ws_msg(method="tools/list", request_id=7), "client-b"
    )
    assert "result" in other
    # A fresh id in the first session is still accepted.
    fresh = await server._handle_websocket_message(
        _ws_msg(method="tools/list", request_id=8), "client-a"
    )
    assert "result" in fresh
