# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""HIGH 1.6: Canonical wire type tests for JSON-RPC 2.0 / MCP protocol messages.

Verifies that JsonRpcRequest, JsonRpcResponse, JsonRpcError, and McpToolInfo
can be constructed, serialized, deserialized, and round-tripped correctly,
and that invalid inputs are rejected with JsonRpcValidationError.
"""

from __future__ import annotations

import pytest

from kailash_mcp.protocol.messages import (
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
    JsonRpcValidationError,
    McpToolInfo,
)


# ---------------------------------------------------------------------------
# JsonRpcError
# ---------------------------------------------------------------------------


class TestJsonRpcError:
    """Tests for JsonRpcError construction, serialization, and validation."""

    def test_construct_valid(self) -> None:
        err = JsonRpcError(code=-32600, message="Invalid request")
        assert err.code == -32600
        assert err.message == "Invalid request"
        assert err.data is None

    def test_construct_with_data(self) -> None:
        err = JsonRpcError(code=-32602, message="Invalid params", data={"field": "x"})
        assert err.data == {"field": "x"}

    def test_to_dict_omits_none_data(self) -> None:
        err = JsonRpcError(code=-32700, message="Parse error")
        d = err.to_dict()
        assert d == {"code": -32700, "message": "Parse error"}
        assert "data" not in d

    def test_to_dict_includes_data(self) -> None:
        err = JsonRpcError(code=-32700, message="Parse error", data=[1, 2])
        d = err.to_dict()
        assert d["data"] == [1, 2]

    def test_from_dict_valid(self) -> None:
        d = {"code": -32601, "message": "Method not found"}
        err = JsonRpcError.from_dict(d)
        assert err.code == -32601
        assert err.message == "Method not found"

    def test_round_trip(self) -> None:
        original = JsonRpcError(
            code=-32603, message="Internal error", data={"trace": "abc"}
        )
        reconstructed = JsonRpcError.from_dict(original.to_dict())
        assert reconstructed.code == original.code
        assert reconstructed.message == original.message
        assert reconstructed.data == original.data

    def test_canonical_json_round_trip(self) -> None:
        original = JsonRpcError(code=-32000, message="Server error")
        json_str = original.to_canonical_json()
        restored = JsonRpcError.from_canonical_json(json_str)
        assert restored.code == original.code
        assert restored.message == original.message

    def test_reject_non_int_code(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="code must be int"):
            JsonRpcError(code="bad", message="x")  # type: ignore[arg-type]

    def test_reject_bool_code(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="code must be int"):
            JsonRpcError(code=True, message="x")  # type: ignore[arg-type]

    def test_reject_non_str_message(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="message must be str"):
            JsonRpcError(code=-1, message=42)  # type: ignore[arg-type]

    def test_from_dict_rejects_non_dict(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="expects dict"):
            JsonRpcError.from_dict([1, 2])  # type: ignore[arg-type]

    def test_from_dict_rejects_missing_fields(self) -> None:
        with pytest.raises(
            JsonRpcValidationError, match="requires 'code' and 'message'"
        ):
            JsonRpcError.from_dict({"code": -1})


# ---------------------------------------------------------------------------
# JsonRpcRequest
# ---------------------------------------------------------------------------


class TestJsonRpcRequest:
    """Tests for JsonRpcRequest construction, serialization, and validation."""

    def test_construct_minimal(self) -> None:
        req = JsonRpcRequest(method="tools/list")
        assert req.method == "tools/list"
        assert req.params is None
        assert req.id is None
        assert req.jsonrpc == "2.0"
        assert req.is_notification is True

    def test_construct_with_id(self) -> None:
        req = JsonRpcRequest(method="tools/call", params={"name": "greet"}, id=42)
        assert req.id == 42
        assert req.is_notification is False
        assert req.params == {"name": "greet"}

    def test_construct_with_string_id(self) -> None:
        req = JsonRpcRequest(method="test", id="req-1")
        assert req.id == "req-1"

    def test_construct_with_list_params(self) -> None:
        req = JsonRpcRequest(method="test", params=[1, 2, 3], id=1)
        assert req.params == [1, 2, 3]

    def test_to_dict_notification(self) -> None:
        req = JsonRpcRequest(method="notify")
        d = req.to_dict()
        assert d == {"jsonrpc": "2.0", "method": "notify"}
        assert "id" not in d
        assert "params" not in d

    def test_to_dict_full(self) -> None:
        req = JsonRpcRequest(method="test", params={"a": 1}, id=5)
        d = req.to_dict()
        assert d == {"jsonrpc": "2.0", "method": "test", "params": {"a": 1}, "id": 5}

    def test_from_dict_valid(self) -> None:
        d = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        req = JsonRpcRequest.from_dict(d)
        assert req.method == "tools/list"
        assert req.id == 1

    def test_round_trip(self) -> None:
        original = JsonRpcRequest(method="tools/call", params={"tool": "x"}, id="r1")
        reconstructed = JsonRpcRequest.from_dict(original.to_dict())
        assert reconstructed.method == original.method
        assert reconstructed.params == original.params
        assert reconstructed.id == original.id

    def test_canonical_json_round_trip(self) -> None:
        original = JsonRpcRequest(method="ping", id=99)
        json_str = original.to_canonical_json()
        restored = JsonRpcRequest.from_canonical_json(json_str)
        assert restored.method == original.method
        assert restored.id == original.id

    def test_reject_wrong_jsonrpc_version(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="must be '2.0'"):
            JsonRpcRequest(method="test", jsonrpc="1.0")

    def test_reject_empty_method(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="non-empty str"):
            JsonRpcRequest(method="")

    def test_reject_non_str_method(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="non-empty str"):
            JsonRpcRequest(method=123)  # type: ignore[arg-type]

    def test_reject_invalid_params_type(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="dict | list | None"):
            JsonRpcRequest(method="test", params="not-a-dict")  # type: ignore[arg-type]

    def test_reject_bool_id(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="must not be bool"):
            JsonRpcRequest(method="test", id=True)  # type: ignore[arg-type]

    def test_reject_float_id(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="str | int | None"):
            JsonRpcRequest(method="test", id=3.14)  # type: ignore[arg-type]

    def test_from_dict_rejects_unknown_fields(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="unknown fields"):
            JsonRpcRequest.from_dict({"method": "test", "extra": True})

    def test_from_dict_rejects_missing_method(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="requires 'method'"):
            JsonRpcRequest.from_dict({"jsonrpc": "2.0"})

    def test_from_dict_rejects_non_dict(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="expects dict"):
            JsonRpcRequest.from_dict("string")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# JsonRpcResponse
# ---------------------------------------------------------------------------


class TestJsonRpcResponse:
    """Tests for JsonRpcResponse construction, serialization, and validation."""

    def test_construct_success(self) -> None:
        resp = JsonRpcResponse(id=1, result={"tools": []})
        assert resp.result == {"tools": []}
        assert resp.error is None
        assert resp.is_error is False

    def test_construct_error(self) -> None:
        err = JsonRpcError(code=-32601, message="Method not found")
        resp = JsonRpcResponse(id=1, error=err)
        assert resp.is_error is True
        assert resp.result is None

    def test_construct_null_id_on_parse_error(self) -> None:
        err = JsonRpcError(code=-32700, message="Parse error")
        resp = JsonRpcResponse(id=None, error=err)
        assert resp.id is None

    def test_to_dict_success(self) -> None:
        resp = JsonRpcResponse(id=1, result="ok")
        d = resp.to_dict()
        assert d == {"jsonrpc": "2.0", "id": 1, "result": "ok"}
        assert "error" not in d

    def test_to_dict_error(self) -> None:
        err = JsonRpcError(code=-32600, message="Invalid request")
        resp = JsonRpcResponse(id=None, error=err)
        d = resp.to_dict()
        assert d["error"] == {"code": -32600, "message": "Invalid request"}
        assert "result" not in d

    def test_from_dict_success(self) -> None:
        d = {"jsonrpc": "2.0", "id": 5, "result": [1, 2, 3]}
        resp = JsonRpcResponse.from_dict(d)
        assert resp.id == 5
        assert resp.result == [1, 2, 3]

    def test_from_dict_error(self) -> None:
        d = {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": "Parse error"},
        }
        resp = JsonRpcResponse.from_dict(d)
        assert resp.is_error is True
        assert resp.error.code == -32700

    def test_round_trip_success(self) -> None:
        original = JsonRpcResponse(id="r1", result={"data": 42})
        reconstructed = JsonRpcResponse.from_dict(original.to_dict())
        assert reconstructed.id == original.id
        assert reconstructed.result == original.result

    def test_round_trip_error(self) -> None:
        err = JsonRpcError(
            code=-32603, message="Internal error", data={"detail": "boom"}
        )
        original = JsonRpcResponse(id=1, error=err)
        reconstructed = JsonRpcResponse.from_dict(original.to_dict())
        assert reconstructed.error.code == -32603
        assert reconstructed.error.data == {"detail": "boom"}

    def test_canonical_json_round_trip(self) -> None:
        original = JsonRpcResponse(id=1, result="hello")
        json_str = original.to_canonical_json()
        restored = JsonRpcResponse.from_canonical_json(json_str)
        assert restored.id == original.id
        assert restored.result == original.result

    def test_reject_both_result_and_error(self) -> None:
        err = JsonRpcError(code=-1, message="x")
        with pytest.raises(JsonRpcValidationError, match="mutually exclusive"):
            JsonRpcResponse(id=1, result="data", error=err)

    def test_reject_neither_result_nor_error(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="exactly one"):
            JsonRpcResponse(id=1)

    def test_reject_bool_id(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="must not be bool"):
            JsonRpcResponse(id=False, result="x")  # type: ignore[arg-type]

    def test_reject_wrong_jsonrpc(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="must be '2.0'"):
            JsonRpcResponse(id=1, result="x", jsonrpc="1.0")

    def test_from_dict_rejects_unknown_fields(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="unknown fields"):
            JsonRpcResponse.from_dict({"id": 1, "result": "x", "extra": True})

    def test_from_dict_rejects_missing_id(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="requires 'id'"):
            JsonRpcResponse.from_dict({"result": "x"})

    def test_from_dict_rejects_non_dict(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="expects dict"):
            JsonRpcResponse.from_dict(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# McpToolInfo
# ---------------------------------------------------------------------------


class TestMcpToolInfo:
    """Tests for McpToolInfo construction, serialization, and validation."""

    def test_construct_minimal(self) -> None:
        tool = McpToolInfo(name="greet", description="Say hello")
        assert tool.name == "greet"
        assert tool.description == "Say hello"
        assert tool.input_schema == {}

    def test_construct_with_schema(self) -> None:
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        tool = McpToolInfo(name="greet", description="Say hello", input_schema=schema)
        assert tool.input_schema == schema

    def test_to_dict_camelcase_wire_format(self) -> None:
        tool = McpToolInfo(
            name="test", description="desc", input_schema={"type": "object"}
        )
        d = tool.to_dict()
        assert "inputSchema" in d
        assert "input_schema" not in d
        assert d == {
            "name": "test",
            "description": "desc",
            "inputSchema": {"type": "object"},
        }

    def test_from_dict_camelcase(self) -> None:
        d = {
            "name": "tool1",
            "description": "A tool",
            "inputSchema": {"type": "object"},
        }
        tool = McpToolInfo.from_dict(d)
        assert tool.name == "tool1"
        assert tool.input_schema == {"type": "object"}

    def test_from_dict_default_schema(self) -> None:
        d = {"name": "tool1", "description": "A tool"}
        tool = McpToolInfo.from_dict(d)
        assert tool.input_schema == {}

    def test_round_trip(self) -> None:
        schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
        original = McpToolInfo(
            name="calc", description="Calculate", input_schema=schema
        )
        reconstructed = McpToolInfo.from_dict(original.to_dict())
        assert reconstructed.name == original.name
        assert reconstructed.description == original.description
        assert reconstructed.input_schema == original.input_schema

    def test_canonical_json_round_trip(self) -> None:
        original = McpToolInfo(name="echo", description="Echo back")
        json_str = original.to_canonical_json()
        restored = McpToolInfo.from_canonical_json(json_str)
        assert restored.name == original.name
        assert restored.description == original.description

    def test_reject_empty_name(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="non-empty str"):
            McpToolInfo(name="", description="desc")

    def test_reject_non_str_name(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="non-empty str"):
            McpToolInfo(name=123, description="desc")  # type: ignore[arg-type]

    def test_reject_non_str_description(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="description must be str"):
            McpToolInfo(name="x", description=42)  # type: ignore[arg-type]

    def test_reject_non_dict_schema(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="input_schema must be dict"):
            McpToolInfo(name="x", description="d", input_schema="bad")  # type: ignore[arg-type]

    def test_from_dict_rejects_unknown_fields(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="unknown fields"):
            McpToolInfo.from_dict({"name": "x", "description": "d", "extra": True})

    def test_from_dict_rejects_missing_required(self) -> None:
        with pytest.raises(
            JsonRpcValidationError, match="requires 'name' and 'description'"
        ):
            McpToolInfo.from_dict({"name": "x"})

    def test_from_dict_rejects_non_dict(self) -> None:
        with pytest.raises(JsonRpcValidationError, match="expects dict"):
            McpToolInfo.from_dict("string")  # type: ignore[arg-type]
