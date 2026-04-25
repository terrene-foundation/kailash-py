"""HTTP transport for MCP client communication.

:class:`HttpTransport` sends JSON-RPC requests to an MCP server via
HTTP POST. Each request is a single ``POST`` with
``Content-Type: application/json`` and the response body contains the
JSON-RPC response.

This mirrors the Rust SDK's ``HttpTransport`` (see
``kailash-rs/crates/kailash-mcp/src/transport/http.rs``) for cross-SDK
parity. The wire format is identical — a Python client speaks to a
Rust-served HTTP MCP endpoint and vice versa.

The primary constructor :meth:`HttpTransport.__init__` validates the
endpoint URL via :func:`kailash.channels.mcp.base.validate_url` to
prevent SSRF; only ``http`` and ``https`` schemes are allowed and
private/loopback addresses are rejected unless ``allow_private=True``
is passed (intended for trusted internal endpoints).

HTTP is a request/response transport — :meth:`receive` raises
:class:`NotImplementedError` because the protocol does not support
unsolicited server-push.
"""

from __future__ import annotations

import asyncio
from typing import Optional

import aiohttp

from .base import ProtocolError, Transport, TransportError, validate_url


class HttpTransport(Transport):
    """MCP client transport that sends JSON-RPC requests via HTTP POST.

    Attributes:
        endpoint_url: The validated endpoint URL.
    """

    def __init__(
        self,
        endpoint_url: str,
        *,
        session: Optional[aiohttp.ClientSession] = None,
        allow_private: bool = False,
        timeout: float = 30.0,
        headers: Optional[dict] = None,
    ) -> None:
        """Create an HTTP transport.

        Args:
            endpoint_url: Full MCP endpoint URL.
            session: Optional pre-built :class:`aiohttp.ClientSession`.
                If ``None`` a session is created lazily on first use and
                owned/closed by this transport.
            allow_private: Skip the SSRF check (use only when the URL
                comes from a trusted server-managed source — admin
                registry, internal service mesh).
            timeout: Per-request timeout in seconds.
            headers: Optional default headers added to every POST
                (in addition to ``Content-Type: application/json``).
        """
        validated = validate_url(endpoint_url, allow_private=allow_private)
        self.endpoint_url = validated
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session = session
        self._owns_session = session is None
        self._extra_headers = dict(headers or {})
        self._closed = False

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
            self._owns_session = True
        return self._session

    # ------------------------------------------------------------------
    # Transport protocol
    # ------------------------------------------------------------------

    async def send(self, message: str) -> str:
        """POST ``message`` to the endpoint and return the response body.

        Raises:
            TransportError: On connection failure / timeout.
            ProtocolError: On HTTP 4xx / 5xx response.
        """
        if self._closed:
            raise TransportError("transport is closed")

        session = await self._ensure_session()
        request_headers = {"Content-Type": "application/json"}
        request_headers.update(self._extra_headers)

        try:
            async with session.post(
                self.endpoint_url,
                data=message,
                headers=request_headers,
            ) as response:
                body = await response.text()
                if response.status >= 400:
                    raise ProtocolError(f"HTTP {response.status}: {body}")
                return body
        except asyncio.TimeoutError as exc:
            raise TransportError(
                f"HTTP request to {self.endpoint_url} timed out"
            ) from exc
        except aiohttp.ClientConnectionError as exc:
            raise TransportError(
                f"failed to connect to {self.endpoint_url}: {exc}"
            ) from exc
        except aiohttp.ClientError as exc:
            raise TransportError(
                f"HTTP request to {self.endpoint_url} failed: {exc}"
            ) from exc

    async def receive(self) -> str:
        """HTTP transport does not support unsolicited server messages."""
        raise NotImplementedError(
            "HttpTransport does not support receive() — HTTP is "
            "request/response only. Use SseTransport for server-push."
        )

    async def close(self) -> None:
        """Close the HTTP session if owned."""
        if self._closed:
            return
        self._closed = True
        if self._owns_session and self._session is not None:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None


__all__ = ["HttpTransport"]
