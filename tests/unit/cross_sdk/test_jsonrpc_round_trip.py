# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-SDK JSON-RPC round-trip tests (SPEC-01 §7, SPEC-09 §2.1).

These tests instantiate the canonical ``JsonRpcRequest`` / ``JsonRpcResponse``
/ ``JsonRpcError`` dataclasses from ``kailash_mcp.protocol`` and verify that
their ``to_canonical_json()`` output exactly matches the fixture file that
``kailash-rs`` consumes for cross-SDK parity validation (EATP D6).

Spec-compliance v2 CRITICAL #8 failure class this file guards against:
the previous version serialized a plain ``dict`` via stdlib ``json.dumps``
and never imported the canonical classes. It would pass even if the
canonical classes were missing. This version fails loudly when:

1. The canonical class is not importable.
2. The class's ``to_canonical_json`` drifts from the fixture bytes.
3. ``from_canonical_json`` cannot reconstruct a semantically equal instance.
4. A notification (no ``id``) is mis-handled as a request.
"""

from __future__ import annotations

import json

import pytest
from kailash_mcp.protocol import (
    JSONRPC_VERSION,
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
    JsonRpcValidationError,
    McpToolInfo,
)

# ---------------------------------------------------------------------------
# Request round-trip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename",
    [
        "request_simple.json",
        "request_with_params.json",
        "request_with_params_list.json",
        "request_notification.json",
    ],
)
def test_jsonrpc_request_round_trip(load_vector, filename):
    """Canonical ``JsonRpcRequest`` produces fixture-exact canonical JSON.

    Instantiates ``JsonRpcRequest`` from the fixture ``input`` dict, calls
    ``to_canonical_json``, and asserts byte equality with the fixture's
    ``expected_canonical_json``. Then deserializes via
    ``from_canonical_json`` and asserts object equality (frozen dataclass
    structural equality).
    """
    vector = load_vector("jsonrpc", filename)
    input_obj = vector["input"]
    expected = vector["expected_canonical_json"]

    # Build the canonical class from the fixture dict -- this is the
    # test's whole point: we MUST instantiate JsonRpcRequest, not serialize
    # a plain dict. Fixture drift surfaces here.
    request = JsonRpcRequest.from_dict(input_obj)

    # to_canonical_json must match the fixture byte-for-byte
    actual = request.to_canonical_json()
    assert actual == expected, (
        f"Canonical JSON mismatch for {filename}:\n"
        f"  expected: {expected}\n"
        f"  actual:   {actual}"
    )

    # Round-trip from the canonical JSON back to a dataclass instance
    round_tripped = JsonRpcRequest.from_canonical_json(expected)
    assert round_tripped == request, (
        f"Round-trip inequality for {filename}:\n"
        f"  original:    {request}\n"
        f"  round-trip:  {round_tripped}"
    )

    # Semantic equivalent: same method, same params, same id
    assert round_tripped.method == request.method
    assert round_tripped.params == request.params
    assert round_tripped.id == request.id


def test_jsonrpc_notification_has_no_id(load_vector):
    """A fixture-defined notification round-trips with ``is_notification=True``.

    Per JSON-RPC 2.0 §4.1, a notification has no ``id`` field and MUST NOT
    receive a response. The canonical class exposes this via the
    ``is_notification`` property. Fixture ``request_notification.json``
    MUST round-trip as a notification.
    """
    vector = load_vector("jsonrpc", "request_notification.json")
    request = JsonRpcRequest.from_dict(vector["input"])
    assert request.is_notification is True
    assert request.id is None
    # The serialized form MUST NOT contain an "id" key.
    serialized = json.loads(request.to_canonical_json())
    assert "id" not in serialized


# ---------------------------------------------------------------------------
# Response round-trip
# ---------------------------------------------------------------------------


def test_jsonrpc_response_success_round_trip(load_vector):
    """Success response round-trips through the canonical class."""
    vector = load_vector("jsonrpc", "response_success.json")
    input_obj = vector["input"]
    expected = vector["expected_canonical_json"]

    response = JsonRpcResponse.from_dict(input_obj)
    assert response.is_error is False
    assert response.error is None

    actual = response.to_canonical_json()
    assert actual == expected, (
        f"Canonical JSON mismatch for response_success.json:\n"
        f"  expected: {expected}\n"
        f"  actual:   {actual}"
    )

    round_tripped = JsonRpcResponse.from_canonical_json(expected)
    assert round_tripped == response


def test_jsonrpc_response_error_round_trip(load_vector):
    """Error response round-trips through ``JsonRpcError``."""
    vector = load_vector("jsonrpc", "response_error.json")
    input_obj = vector["input"]
    expected = vector["expected_canonical_json"]

    response = JsonRpcResponse.from_dict(input_obj)
    assert response.is_error is True
    assert isinstance(response.error, JsonRpcError)
    # The fixture uses the standard METHOD_NOT_FOUND code per SPEC-01 §7.4.
    assert response.error.code == JsonRpcError.METHOD_NOT_FOUND

    actual = response.to_canonical_json()
    assert actual == expected, (
        f"Canonical JSON mismatch for response_error.json:\n"
        f"  expected: {expected}\n"
        f"  actual:   {actual}"
    )

    round_tripped = JsonRpcResponse.from_canonical_json(expected)
    assert round_tripped == response


# ---------------------------------------------------------------------------
# McpToolInfo round-trip (SPEC-01 §7 + MCP Tool shape)
# ---------------------------------------------------------------------------


def test_mcp_tool_info_round_trip():
    """``McpToolInfo`` round-trip produces the MCP spec ``Tool`` wire shape.

    Instantiated directly (no fixture) because this verifies the class
    internals produce the expected canonical form. The matching Rust test
    uses the same literal values and asserts the same canonical bytes.
    """
    tool = McpToolInfo(
        name="read_file",
        description="Read a file",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    )
    # The canonical form uses camelCase "inputSchema" per MCP spec.
    canonical = tool.to_canonical_json()
    expected = (
        '{"description":"Read a file",'
        '"inputSchema":{"properties":{"path":{"type":"string"}},'
        '"required":["path"],"type":"object"},'
        '"name":"read_file"}'
    )
    assert (
        canonical == expected
    ), f"McpToolInfo canonical JSON drift:\n  expected: {expected}\n  actual:   {canonical}"
    round_tripped = McpToolInfo.from_canonical_json(canonical)
    assert round_tripped == tool


# ---------------------------------------------------------------------------
# Structural validation failure modes
# ---------------------------------------------------------------------------


def test_jsonrpc_request_rejects_wrong_version():
    """Mismatched ``jsonrpc`` version is a structural validation error.

    Per JSON-RPC 2.0 §4, the version field MUST equal ``"2.0"``. A mismatch
    is a loud failure -- the canonical class MUST raise rather than silently
    accept a ``"3.0"`` payload that one SDK might honor and another reject
    (SPEC-09 §8.3 wire format drift mitigation).
    """
    with pytest.raises(JsonRpcValidationError, match="jsonrpc"):
        JsonRpcRequest(method="tools/list", id=1, jsonrpc="3.0")


def test_jsonrpc_request_rejects_unknown_fields():
    """Unknown top-level fields are rejected by ``from_dict``."""
    with pytest.raises(JsonRpcValidationError, match="unknown fields"):
        JsonRpcRequest.from_dict(
            {
                "jsonrpc": JSONRPC_VERSION,
                "method": "tools/list",
                "id": 1,
                "batch": True,  # unknown field
            }
        )


def test_jsonrpc_response_rejects_both_result_and_error():
    """A response with both ``result`` and ``error`` is invalid per §5."""
    err = JsonRpcError(code=-32603, message="Internal error")
    with pytest.raises(JsonRpcValidationError, match="mutually exclusive"):
        JsonRpcResponse(id=1, result={"ok": True}, error=err)


def test_jsonrpc_response_rejects_neither_result_nor_error():
    """A response with neither ``result`` nor ``error`` is invalid per §5."""
    with pytest.raises(JsonRpcValidationError, match="exactly one"):
        JsonRpcResponse(id=1)


def test_jsonrpc_request_rejects_bool_id():
    """A bool id is ambiguous (bool is an ``int`` subtype in Python).

    Per JSON-RPC 2.0 §4, ``id`` is a string, number, or null. ``True`` and
    ``False`` serialize as ``true``/``false`` -- neither. Accepting them
    would produce a payload the Rust SDK rejects, creating a parser
    differential per SPEC-09 §8.2.
    """
    with pytest.raises(JsonRpcValidationError, match="not be bool"):
        JsonRpcRequest(method="tools/list", id=True)


# ---------------------------------------------------------------------------
# Strict parser differential guard (SPEC-09 §8.2)
# ---------------------------------------------------------------------------


def test_jsonrpc_from_canonical_json_uses_strict_mode():
    """``from_canonical_json`` MUST reject invalid control characters.

    SPEC-09 §8.2 mandates ``strict=True`` parsing so the Python and Rust
    parsers reach the same conclusion on every input. Python's default
    ``strict=True`` rejects raw control characters inside strings; a
    payload containing a bare newline inside a JSON string is a loud
    failure here.
    """
    bad_payload = '{"jsonrpc":"2.0","method":"a\nb","id":1}'
    with pytest.raises(json.JSONDecodeError):
        JsonRpcRequest.from_canonical_json(bad_payload)


def test_jsonrpc_error_code_constants():
    """The class-level constants match the JSON-RPC 2.0 standard codes."""
    assert JsonRpcError.PARSE_ERROR == -32700
    assert JsonRpcError.INVALID_REQUEST == -32600
    assert JsonRpcError.METHOD_NOT_FOUND == -32601
    assert JsonRpcError.INVALID_PARAMS == -32602
    assert JsonRpcError.INTERNAL_ERROR == -32603
