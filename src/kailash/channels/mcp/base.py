"""Transport abstractions for MCP client-server communication.

The :class:`Transport` abstract base hides the physical wire (stdio
subprocess, HTTP, SSE, in-memory test queue) behind a single async
``send`` call. The MCP client dispatches JSON-RPC requests through any
implementation; the underlying I/O is an implementation detail.

This mirrors the Rust SDK's ``McpTransport`` trait (see
``kailash-rs/crates/kailash-mcp/src/transport/mod.rs``) for cross-SDK
parity (EATP D6: independent implementation, matching semantics).

Three concrete transports ship in this package:

- :class:`~kailash.channels.mcp.stdio.StdioTransport` — bidirectional
  stdin/stdout JSON-RPC framing (LSP-style ``Content-Length`` headers).
- :class:`~kailash.channels.mcp.sse.SseTransport` — Server-Sent Events
  client (HTTP POST for client→server, SSE for server→client).
- :class:`~kailash.channels.mcp.http.HttpTransport` — HTTP POST request /
  response (single-shot per-message).

All transports validate user-supplied URLs for SSRF before connecting.
See :func:`validate_url` for the policy.
"""

from __future__ import annotations

import ipaddress
from abc import ABC, abstractmethod
from typing import Optional
from urllib.parse import urlparse


class TransportError(Exception):
    """Base class for transport-layer failures.

    Raised by :class:`Transport` implementations when the underlying I/O
    fails (connection refused, EOF, framing error, malformed response).
    Subclasses :class:`ConnectionError` so callers can ``except
    ConnectionError`` if they prefer the stdlib base.
    """


class ProtocolError(TransportError):
    """JSON-RPC framing or HTTP-status protocol violation.

    Distinct from :class:`TransportError` for callers that want to
    distinguish "transport down" (retry) from "server returned a 4xx /
    5xx" (don't retry).
    """


class Transport(ABC):
    """Abstract MCP transport.

    Implementations send a JSON-encoded JSON-RPC request and return the
    JSON-encoded response. The transport layer is responsible only for
    framing and delivery — JSON parsing and method dispatch live in the
    MCP client / server layer above.

    All implementations MUST be safe to share across asyncio tasks; the
    concrete transports use locks where needed (stdio's stdin/stdout)
    or stateless HTTP clients (sse/http).
    """

    @abstractmethod
    async def send(self, message: str) -> str:
        """Send a JSON-RPC request and return the JSON-RPC response.

        Args:
            message: JSON-encoded JSON-RPC request string.

        Returns:
            JSON-encoded JSON-RPC response string.

        Raises:
            TransportError: If the underlying I/O fails.
            ProtocolError: If the framing or HTTP status indicates a
                protocol-level violation.
        """
        raise NotImplementedError

    @abstractmethod
    async def receive(self) -> str:
        """Receive a single JSON-RPC message from the server.

        Used by transports that support server→client push (SSE event
        stream, stdio out-of-band notifications). Transports that are
        strictly request/response (plain HTTP) MAY raise
        :class:`NotImplementedError` from ``receive``.

        Returns:
            JSON-encoded JSON-RPC message string.

        Raises:
            TransportError: If the underlying I/O fails.
            NotImplementedError: If the transport does not support
                unsolicited server messages.
        """
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Close the transport and release underlying resources.

        Idempotent — calling :meth:`close` after the transport is
        already closed is a no-op.
        """
        raise NotImplementedError

    async def __aenter__(self) -> "Transport":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()


# ---------------------------------------------------------------------------
# SSRF validation — shared by HTTP and SSE transports.
#
# Mirrors the Rust ``transport::validate_url`` policy: only ``http`` and
# ``https`` schemes; reject private / loopback / link-local addresses
# unless the caller opts in via ``allow_private=True`` (intended for
# internal service-mesh use).
# ---------------------------------------------------------------------------


def validate_url(raw_url: str, *, allow_private: bool = False) -> str:
    """Validate ``raw_url`` for outbound MCP transport use.

    Rules:

    - Only ``http`` and ``https`` schemes are allowed.
    - Unless ``allow_private`` is True, hosts that resolve syntactically
      to a private, loopback, or link-local address are rejected.

    DNS rebinding caveat: this check validates the URL **syntactically**
    but does not resolve DNS. A hostname that DNS-resolves to a private
    IP at connect time bypasses this check; pair with a DNS-aware
    resolver if defense-in-depth is required.

    Args:
        raw_url: The candidate endpoint URL.
        allow_private: If True, skip the private/loopback/link-local
            check. Use only for endpoints from a trusted server-managed
            source (admin-configured registry, internal service mesh).

    Returns:
        The normalized URL string (``parsed.geturl()`` form).

    Raises:
        TransportError: If the URL fails validation.
    """
    if not isinstance(raw_url, str) or not raw_url:
        raise TransportError("URL must be a non-empty string")

    try:
        parsed = urlparse(raw_url)
    except ValueError as exc:
        raise TransportError(f"invalid URL: {exc}") from exc

    if parsed.scheme not in ("http", "https"):
        raise TransportError(
            f"unsupported URL scheme {parsed.scheme!r}: only http and https are allowed"
        )

    host = parsed.hostname
    if not host:
        raise TransportError("URL has no host")

    if not allow_private and _is_private_host(host):
        raise TransportError("URL points to private network")

    return parsed.geturl()


def _is_private_host(host: str) -> bool:
    """Return True if ``host`` is a private/loopback/link-local address.

    Handles raw IPv4, raw IPv6 (with brackets stripped by urlparse), and
    well-known loopback hostnames (``localhost`` / ``*.localhost``).
    Real hostnames that are not loopback fall through to False — DNS
    rebinding is the caller's responsibility (see :func:`validate_url`).
    """
    # Try parsing as IP first.
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None

    if ip is not None:
        return ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_unspecified

    lower = host.lower()
    if lower == "localhost" or lower.endswith(".localhost"):
        return True

    return False


__all__ = [
    "Transport",
    "TransportError",
    "ProtocolError",
    "validate_url",
]
