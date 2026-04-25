# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""MCP transport primitives — client side.

Three concrete transports speak the JSON-RPC wire protocol over
different physical layers:

- :class:`StdioTransport` — bidirectional stdin/stdout JSON-RPC framing
  (LSP ``Content-Length`` framing) against a local subprocess MCP
  server.
- :class:`SseTransport` — HTTP POST + Server-Sent Events stream
  against a remote SSE-exposed MCP server.
- :class:`HttpTransport` — single-shot HTTP POST request/response
  against a remote HTTP MCP endpoint (no server-push).

All transports satisfy the :class:`Transport` ABC and may be passed
to any consumer that accepts a ``Transport`` instance (kaizen, the
MCP client utilities, etc.).

This module mirrors the Rust SDK's ``kailash-mcp/src/transport/``
crate for cross-SDK parity (EATP D6: independent implementation,
matching wire semantics).
"""

from kailash.channels.mcp.base import (
    ProtocolError,
    Transport,
    TransportError,
    validate_url,
)
from kailash.channels.mcp.http import HttpTransport
from kailash.channels.mcp.sse import SseTransport
from kailash.channels.mcp.stdio import StdioTransport

__all__ = [
    "HttpTransport",
    "ProtocolError",
    "SseTransport",
    "StdioTransport",
    "Transport",
    "TransportError",
    "validate_url",
]
