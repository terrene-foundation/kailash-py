# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Canonical JSON-RPC 2.0 and MCP wire types (SPEC-01 §7, SPEC-09 §2.1).

This module defines the single source of truth for JSON-RPC / MCP wire
format in Python. Both ``kailash-py`` and ``kailash-rs`` MUST produce
byte-identical canonical JSON for the same logical input per EATP D6.

The canonical form used for cross-SDK round-trip comparison is:

- Keys sorted alphabetically
- No insignificant whitespace (``separators=(",", ":")``)
- ``null`` for explicitly-absent fields (NOT omitted) only where the
  protocol spec requires it; optional fields with ``None`` value are
  omitted from the serialized output
- Integer error codes as JSON numbers (no string coercion)
- ``strict=True`` parsing rejects duplicate keys / BOMs / trailing commas

Classes
-------
``JsonRpcError``
    Frozen dataclass for JSON-RPC error objects (code, message, data).
``JsonRpcRequest``
    Frozen dataclass for JSON-RPC request and notification messages.
``JsonRpcResponse``
    Frozen dataclass for JSON-RPC response messages (success or error).
``McpToolInfo``
    Frozen dataclass for MCP ``tools/list`` and ``tools/call`` tool metadata.

Every class exposes ``to_dict``/``from_dict`` (round-trip preserving) and
``to_canonical_json``/``from_canonical_json`` (byte-stable cross-SDK form).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, ClassVar

logger = logging.getLogger(__name__)

__all__ = [
    "JsonRpcError",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "McpToolInfo",
    "JsonRpcValidationError",
]

# JSON-RPC 2.0 protocol version. Both SDKs MUST emit this exact string.
JSONRPC_VERSION: str = "2.0"


class JsonRpcValidationError(ValueError):
    """Raised when a JSON-RPC payload fails canonical validation.

    Distinct from ``MCPError`` (which is the runtime error surface) because
    validation errors are structural -- they indicate a malformed wire
    message, not a remote method failure.
    """


# ---------------------------------------------------------------------------
# JsonRpcError
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JsonRpcError:
    """Canonical JSON-RPC 2.0 error object (per JSON-RPC 2.0 §5.1).

    Attributes
    ----------
    code:
        Integer error code. Standard JSON-RPC codes are provided as class
        constants (``PARSE_ERROR``, ``INVALID_REQUEST``, ...). Values in the
        range ``-32768..-32000`` are reserved for JSON-RPC; values outside
        that range are application-defined.
    message:
        Short human-readable error description.
    data:
        Optional structured error payload. May be ``None``.
    """

    code: int
    message: str
    data: Any | None = None

    # Standard JSON-RPC 2.0 error codes (reserved range -32768..-32000)
    PARSE_ERROR: ClassVar[int] = -32700
    INVALID_REQUEST: ClassVar[int] = -32600
    METHOD_NOT_FOUND: ClassVar[int] = -32601
    INVALID_PARAMS: ClassVar[int] = -32602
    INTERNAL_ERROR: ClassVar[int] = -32603
    # Server errors (reserved sub-range -32099..-32000)
    SERVER_ERROR: ClassVar[int] = -32000

    def __post_init__(self) -> None:
        if not isinstance(self.code, int) or isinstance(self.code, bool):
            raise JsonRpcValidationError(
                f"JsonRpcError.code must be int, got {type(self.code).__name__}"
            )
        if not isinstance(self.message, str):
            raise JsonRpcValidationError(
                f"JsonRpcError.message must be str, got {type(self.message).__name__}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a round-trip dict (omits ``data`` when ``None``)."""
        result: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            result["data"] = self.data
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JsonRpcError:
        """Parse a JSON-RPC error object with strict field validation."""
        if not isinstance(data, dict):
            raise JsonRpcValidationError(
                f"JsonRpcError.from_dict expects dict, got {type(data).__name__}"
            )
        if "code" not in data or "message" not in data:
            raise JsonRpcValidationError(
                "JsonRpcError requires 'code' and 'message' fields"
            )
        return cls(
            code=data["code"],
            message=data["message"],
            data=data.get("data"),
        )

    def to_canonical_json(self) -> str:
        """Deterministic JSON (sorted keys, no whitespace) for cross-SDK use."""
        return json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    @classmethod
    def from_canonical_json(cls, payload: str) -> JsonRpcError:
        """Parse a canonical JSON string into a ``JsonRpcError``."""
        data = json.loads(payload, strict=True)
        return cls.from_dict(data)


# ---------------------------------------------------------------------------
# JsonRpcRequest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JsonRpcRequest:
    """Canonical JSON-RPC 2.0 request or notification message.

    Per JSON-RPC 2.0 §4, a request with no ``id`` field is a *notification*
    that MUST NOT receive a response. Both SDKs represent notifications as a
    ``JsonRpcRequest`` with ``id=None`` and a ``is_notification`` property.

    Attributes
    ----------
    method:
        Name of the method being invoked (e.g. ``"tools/list"``).
    params:
        Optional parameters -- may be a by-name ``dict``, a by-position
        ``list``, or ``None`` (no params).
    id:
        Optional request identifier -- ``str``, ``int``, or ``None`` (for
        notifications). MUST NOT be a ``bool`` per JSON-RPC 2.0 §4.
    jsonrpc:
        Protocol version. MUST equal ``"2.0"``; enforced in ``__post_init__``.
    """

    method: str
    params: dict[str, Any] | list[Any] | None = None
    id: str | int | None = None
    jsonrpc: str = JSONRPC_VERSION

    def __post_init__(self) -> None:
        if self.jsonrpc != JSONRPC_VERSION:
            raise JsonRpcValidationError(
                f"JsonRpcRequest.jsonrpc must be {JSONRPC_VERSION!r}, "
                f"got {self.jsonrpc!r}"
            )
        if not isinstance(self.method, str) or not self.method:
            raise JsonRpcValidationError(
                f"JsonRpcRequest.method must be a non-empty str, got {self.method!r}"
            )
        if self.params is not None and not isinstance(self.params, (dict, list)):
            raise JsonRpcValidationError(
                f"JsonRpcRequest.params must be dict | list | None, "
                f"got {type(self.params).__name__}"
            )
        if self.id is not None and not isinstance(self.id, (str, int)):
            raise JsonRpcValidationError(
                f"JsonRpcRequest.id must be str | int | None, "
                f"got {type(self.id).__name__}"
            )
        # JSON-RPC 2.0 forbids bool-typed ids (bool is an int subtype in Python)
        if isinstance(self.id, bool):
            raise JsonRpcValidationError("JsonRpcRequest.id must not be bool")

    @property
    def is_notification(self) -> bool:
        """True if this request is a JSON-RPC notification (no ``id``)."""
        return self.id is None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a round-trip dict.

        Field inclusion rules (per JSON-RPC 2.0 §4):
        - ``jsonrpc`` always present
        - ``method`` always present
        - ``params`` only if not ``None``
        - ``id`` only if not ``None`` (absent id = notification)
        """
        result: dict[str, Any] = {
            "jsonrpc": self.jsonrpc,
            "method": self.method,
        }
        if self.params is not None:
            result["params"] = self.params
        if self.id is not None:
            result["id"] = self.id
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JsonRpcRequest:
        """Parse a JSON-RPC request dict with strict validation.

        Unknown top-level fields are rejected to catch cross-SDK drift
        early (per SPEC-09 §8.3 wire format drift mitigation).
        """
        if not isinstance(data, dict):
            raise JsonRpcValidationError(
                f"JsonRpcRequest.from_dict expects dict, got {type(data).__name__}"
            )
        known = {"jsonrpc", "method", "params", "id"}
        unknown = set(data.keys()) - known
        if unknown:
            raise JsonRpcValidationError(
                f"JsonRpcRequest: unknown fields {sorted(unknown)}; "
                f"known fields: {sorted(known)}"
            )
        if "method" not in data:
            raise JsonRpcValidationError("JsonRpcRequest requires 'method' field")
        return cls(
            method=data["method"],
            params=data.get("params"),
            id=data.get("id"),
            jsonrpc=data.get("jsonrpc", JSONRPC_VERSION),
        )

    def to_canonical_json(self) -> str:
        """Canonical JSON (sorted keys, no whitespace) per SPEC-09 §2.1."""
        return json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    @classmethod
    def from_canonical_json(cls, payload: str) -> JsonRpcRequest:
        """Parse a canonical JSON string into a ``JsonRpcRequest``.

        Uses ``strict=True`` per SPEC-09 §8.2 to reject duplicate keys,
        BOMs, and trailing commas (JSON parser differential mitigation).
        """
        data = json.loads(payload, strict=True)
        return cls.from_dict(data)


# ---------------------------------------------------------------------------
# JsonRpcResponse
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JsonRpcResponse:
    """Canonical JSON-RPC 2.0 response message.

    Per JSON-RPC 2.0 §5, a response contains *either* ``result`` OR ``error``
    -- never both, never neither. ``__post_init__`` enforces this invariant.

    Attributes
    ----------
    id:
        Request identifier the response corresponds to. MAY be ``None`` only
        if the response is an error generated before the id could be parsed
        (e.g. parse error). Otherwise MUST match the originating request id.
    result:
        Method call result (any JSON value). MUST be ``None`` when ``error``
        is set.
    error:
        Structured error object. MUST be ``None`` when ``result`` is set.
    jsonrpc:
        Protocol version. MUST equal ``"2.0"``.
    """

    id: str | int | None
    result: Any = None
    error: JsonRpcError | None = None
    jsonrpc: str = JSONRPC_VERSION

    def __post_init__(self) -> None:
        if self.jsonrpc != JSONRPC_VERSION:
            raise JsonRpcValidationError(
                f"JsonRpcResponse.jsonrpc must be {JSONRPC_VERSION!r}, "
                f"got {self.jsonrpc!r}"
            )
        if self.id is not None and not isinstance(self.id, (str, int)):
            raise JsonRpcValidationError(
                f"JsonRpcResponse.id must be str | int | None, "
                f"got {type(self.id).__name__}"
            )
        if isinstance(self.id, bool):
            raise JsonRpcValidationError("JsonRpcResponse.id must not be bool")
        if self.error is not None and not isinstance(self.error, JsonRpcError):
            raise JsonRpcValidationError(
                f"JsonRpcResponse.error must be JsonRpcError | None, "
                f"got {type(self.error).__name__}"
            )
        # Exactly one of result/error MUST be set.
        has_result = self.result is not None
        has_error = self.error is not None
        if has_result and has_error:
            raise JsonRpcValidationError(
                "JsonRpcResponse: 'result' and 'error' are mutually exclusive"
            )
        if not has_result and not has_error:
            raise JsonRpcValidationError(
                "JsonRpcResponse: exactly one of 'result' or 'error' is required"
            )

    @property
    def is_error(self) -> bool:
        """True if this response carries an error object."""
        return self.error is not None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a round-trip dict.

        Field inclusion rules (per JSON-RPC 2.0 §5):
        - ``jsonrpc`` always present
        - ``id`` always present (may be explicit ``null`` for parse errors)
        - Exactly one of ``result`` / ``error`` present
        """
        result: dict[str, Any] = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error is not None:
            result["error"] = self.error.to_dict()
        else:
            result["result"] = self.result
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JsonRpcResponse:
        """Parse a JSON-RPC response dict with strict validation."""
        if not isinstance(data, dict):
            raise JsonRpcValidationError(
                f"JsonRpcResponse.from_dict expects dict, got {type(data).__name__}"
            )
        known = {"jsonrpc", "id", "result", "error"}
        unknown = set(data.keys()) - known
        if unknown:
            raise JsonRpcValidationError(
                f"JsonRpcResponse: unknown fields {sorted(unknown)}; "
                f"known fields: {sorted(known)}"
            )
        if "id" not in data:
            raise JsonRpcValidationError("JsonRpcResponse requires 'id' field")
        has_result = "result" in data
        has_error = "error" in data
        if has_result == has_error:
            raise JsonRpcValidationError(
                "JsonRpcResponse: exactly one of 'result' or 'error' is required"
            )
        error = JsonRpcError.from_dict(data["error"]) if has_error else None
        return cls(
            id=data["id"],
            result=data.get("result"),
            error=error,
            jsonrpc=data.get("jsonrpc", JSONRPC_VERSION),
        )

    def to_canonical_json(self) -> str:
        """Canonical JSON (sorted keys, no whitespace) per SPEC-09 §2.1."""
        return json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    @classmethod
    def from_canonical_json(cls, payload: str) -> JsonRpcResponse:
        """Parse a canonical JSON string into a ``JsonRpcResponse``."""
        data = json.loads(payload, strict=True)
        return cls.from_dict(data)


# ---------------------------------------------------------------------------
# McpToolInfo
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class McpToolInfo:
    """Canonical MCP tool descriptor (per MCP spec ``Tool`` object).

    Used in ``tools/list`` responses and as the target of ``tools/call``.
    Matches the JSON shape emitted by the Rust ``kailash_mcp::protocol::
    McpToolInfo`` struct.

    Attributes
    ----------
    name:
        Tool name (unique within a server). Non-empty ASCII string.
    description:
        Human-readable tool description.
    input_schema:
        JSON Schema dict describing the tool's input arguments. The MCP
        spec wire field is ``"inputSchema"`` (camelCase); ``to_dict`` /
        ``from_dict`` handle the snake_case<->camelCase conversion.
    """

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise JsonRpcValidationError(
                f"McpToolInfo.name must be a non-empty str, got {self.name!r}"
            )
        if not isinstance(self.description, str):
            raise JsonRpcValidationError(
                f"McpToolInfo.description must be str, "
                f"got {type(self.description).__name__}"
            )
        if not isinstance(self.input_schema, dict):
            raise JsonRpcValidationError(
                f"McpToolInfo.input_schema must be dict, "
                f"got {type(self.input_schema).__name__}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the MCP spec wire shape (camelCase ``inputSchema``)."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> McpToolInfo:
        """Parse an MCP tool descriptor with strict validation."""
        if not isinstance(data, dict):
            raise JsonRpcValidationError(
                f"McpToolInfo.from_dict expects dict, got {type(data).__name__}"
            )
        known = {"name", "description", "inputSchema"}
        unknown = set(data.keys()) - known
        if unknown:
            raise JsonRpcValidationError(
                f"McpToolInfo: unknown fields {sorted(unknown)}; "
                f"known fields: {sorted(known)}"
            )
        if "name" not in data or "description" not in data:
            raise JsonRpcValidationError(
                "McpToolInfo requires 'name' and 'description' fields"
            )
        return cls(
            name=data["name"],
            description=data["description"],
            input_schema=data.get("inputSchema", {}),
        )

    def to_canonical_json(self) -> str:
        """Canonical JSON (sorted keys, no whitespace) for cross-SDK use."""
        return json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    @classmethod
    def from_canonical_json(cls, payload: str) -> McpToolInfo:
        """Parse a canonical JSON string into an ``McpToolInfo``."""
        data = json.loads(payload, strict=True)
        return cls.from_dict(data)
