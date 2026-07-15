"""Server-Sent Events (SSE) transport — client side.

:class:`SseTransport` connects to a remote MCP server exposing its
JSON-RPC messages over a bidirectional HTTP-POST + SSE stream. The
client POSTs requests to ``{base_url}/message`` and reads responses
either inline (for synchronous servers) or from a Server-Sent Events
stream at ``{base_url}/sse``.

This mirrors the Rust SDK's ``SseClientTransport`` (see
``kailash-rs/crates/kailash-mcp/src/transport/sse.rs``) for cross-SDK
parity.

All constructors validate the base URL via
:func:`kailash.channels.mcp.base.validate_url` to prevent SSRF; only
``http`` and ``https`` schemes are allowed and private/loopback
addresses are rejected unless ``allow_private=True`` is passed.

The full nexus SSE *server* (route registration, middleware, tool
catalogue) lives in ``kailash.middleware.mcp``; this module hosts only
the *client* side so any consumer (kaizen, mcp_executor, etc.) can speak
to remote SSE-exposed MCP servers.
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional

# `aiohttp` is an OPTIONAL dependency under the `server` extra. Per
# `rules/dependencies.md` § "Declared = Imported": optional-extra imports
# MUST raise loudly with an actionable error naming the extra.
try:
    import aiohttp
except ImportError as exc:  # pragma: no cover — covered by structural invariant test
    raise ImportError(
        "kailash.channels.mcp.sse requires server dependencies (aiohttp). "
        "Install with: pip install 'kailash[server]'"
    ) from exc

from .base import ProtocolError, Transport, TransportError, validate_url

# Upper bound on the server-supplied SSE ``retry:`` reconnection delay
# (milliseconds). The server sends this value verbatim; without a ceiling a
# malicious or misconfigured server could pin the client into an arbitrarily
# long reconnect wait (a denial-of-service on the client's own reconnect
# path). Any parsed value above this ceiling is clamped to it (5 minutes).
MAX_RECONNECT_MS = 300_000


class SseTransport(Transport):
    """MCP client transport over Server-Sent Events.

    The client does an HTTP POST to ``{base}/message`` for each request.
    The response body may be either:

    - A plain JSON document (a server that answers synchronously).
    - A single ``data: <json>`` SSE event line — the leading ``data:``
      prefix is stripped before returning to the caller.

    For unsolicited server-push notifications, call :meth:`receive` to
    iterate the ``{base}/sse`` event stream.

    Attributes:
        base_url: The validated base URL (no trailing slash).
        message_path: Endpoint path for POSTed requests (default
            ``/message``).
        sse_path: Endpoint path for the SSE event stream (default
            ``/sse``).
    """

    def __init__(
        self,
        base_url: str,
        *,
        message_path: str = "/message",
        sse_path: str = "/sse",
        session: Optional[aiohttp.ClientSession] = None,
        allow_private: bool = False,
        timeout: float = 30.0,
    ) -> None:
        """Create an SSE transport.

        Args:
            base_url: Base URL of the remote MCP server.
            message_path: Path for client→server POSTs.
            sse_path: Path for the SSE event stream.
            session: Optional pre-built :class:`aiohttp.ClientSession`.
                If ``None`` a session is created lazily on first use and
                owned/closed by this transport.
            allow_private: Skip the SSRF check (intended for trusted
                internal endpoints).
            timeout: Request timeout in seconds.
        """
        validated = validate_url(base_url, allow_private=allow_private)
        self.base_url = validated.rstrip("/")
        self.message_path = (
            message_path if message_path.startswith("/") else f"/{message_path}"
        )
        self.sse_path = sse_path if sse_path.startswith("/") else f"/{sse_path}"
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session = session
        self._owns_session = session is None
        self._closed = False
        self._sse_response: Optional[aiohttp.ClientResponse] = None
        self._sse_lock = asyncio.Lock()
        # Server-requested reconnection delay from the SSE ``retry:`` field
        # (milliseconds). ``None`` until the server sends a ``retry:`` line.
        # MCP requires clients to respect this reconnection time; the value
        # is honored as a delay before re-opening a closed SSE stream.
        self._reconnect_delay_ms: Optional[int] = None
        # Whether the SSE stream has been opened at least once, so the
        # reconnection delay is applied only on an actual re-open, never on
        # the first connection.
        self._sse_opened_once = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
            self._owns_session = True
        return self._session

    @property
    def message_url(self) -> str:
        return f"{self.base_url}{self.message_path}"

    @property
    def sse_url(self) -> str:
        return f"{self.base_url}{self.sse_path}"

    @property
    def reconnect_delay_ms(self) -> Optional[int]:
        """Server-requested SSE reconnection delay in milliseconds.

        Populated from the SSE ``retry:`` field the server sends on the
        event stream; ``None`` until the server sends one. The transport
        waits this long before re-opening a closed SSE stream.
        """
        return self._reconnect_delay_ms

    # ------------------------------------------------------------------
    # Transport protocol
    # ------------------------------------------------------------------

    async def send(self, message: str) -> str:
        """POST ``message`` to ``{base}/message`` and return the body."""
        if self._closed:
            raise TransportError("transport is closed")

        session = await self._ensure_session()
        try:
            async with session.post(
                self.message_url,
                data=message,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
            ) as response:
                text = await response.text()
                if response.status >= 400:
                    raise ProtocolError(
                        f"SSE POST returned HTTP {response.status}: {text}"
                    )
        except aiohttp.ClientError as exc:
            raise TransportError(
                f"SSE POST to {self.message_url} failed: {exc}"
            ) from exc
        except asyncio.TimeoutError as exc:
            raise TransportError(f"SSE POST to {self.message_url} timed out") from exc

        return _strip_sse_data_prefix(text)

    async def receive(self) -> str:
        """Read the next event from the ``{base}/sse`` event stream.

        Opens the SSE connection lazily on first call. Subsequent calls
        consume successive events from the same stream. The raw
        ``data:`` line is returned (already stripped of the prefix).

        Raises:
            TransportError: On connection failure or stream EOF.
            ProtocolError: On malformed SSE framing.
        """
        if self._closed:
            raise TransportError("transport is closed")

        async with self._sse_lock:
            session = await self._ensure_session()
            if self._sse_response is None or self._sse_response.closed:
                # Honor the server-requested reconnection delay (the SSE
                # ``retry:`` field) before RE-opening a closed stream. The
                # first open is never delayed.
                if self._sse_opened_once and self._reconnect_delay_ms is not None:
                    await asyncio.sleep(self._reconnect_delay_ms / 1000.0)
                try:
                    self._sse_response = await session.get(
                        self.sse_url,
                        headers={"Accept": "text/event-stream"},
                    )
                except aiohttp.ClientError as exc:
                    raise TransportError(
                        f"failed to open SSE stream at {self.sse_url}: {exc}"
                    ) from exc
                self._sse_opened_once = True
                if self._sse_response.status >= 400:
                    text = await self._sse_response.text()
                    self._sse_response.release()
                    self._sse_response = None
                    raise ProtocolError(
                        f"SSE GET returned HTTP {self._sse_response.status if self._sse_response else '???'}: {text}"
                    )

            event = await self._read_event(self._sse_response.content)
            if event is None:
                raise TransportError("SSE stream closed before delivering an event")
            return event

    async def _read_event(self, line_source) -> Optional[str]:
        """Read one SSE event from an async line source.

        Consumes decoded ``bytes`` lines from ``line_source`` (an async
        iterator such as :attr:`aiohttp.ClientResponse.content`) until an
        event boundary (a blank line following ``data:`` lines). When the
        stream sends a ``retry:`` field, :attr:`reconnect_delay_ms` is
        updated so a subsequent reconnect honors the server's requested
        reconnection time (per the SSE specification and the MCP transport
        requirement that clients respect ``retry:``).

        Returns the joined ``data:`` payload for the event, or ``None`` if
        the stream ended before a complete event was delivered.
        """
        data_lines: list[str] = []
        async for raw_line in line_source:
            line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
            if line == "":
                if data_lines:
                    return "\n".join(data_lines)
                continue
            if line.startswith(":"):
                # SSE comment line — ignore.
                continue
            if line.startswith("data:"):
                data_lines.append(line[len("data:") :].lstrip())
                continue
            if line.startswith("retry:"):
                delay = _parse_sse_retry_field(line[len("retry:") :])
                if delay is not None:
                    # Clamp the server-supplied reconnection delay to a sane
                    # ceiling so a malicious/misconfigured server cannot pin
                    # the client into an arbitrarily long reconnect wait (DoS).
                    # Negative / non-digit values are already rejected by the
                    # parser (return None), leaving the prior default in place.
                    self._reconnect_delay_ms = min(delay, MAX_RECONNECT_MS)
                continue
            # Any other field (event:, id:) is ignored for the JSON-RPC
            # payload purposes.
        return None

    async def close(self) -> None:
        """Close the SSE stream and (if owned) the HTTP session."""
        if self._closed:
            return
        self._closed = True

        if self._sse_response is not None and not self._sse_response.closed:
            try:
                self._sse_response.release()
            except Exception:
                # Expected-failure cleanup (zero-tolerance Rule 3 carve-out):
                # releasing an already-broken response must not mask close().
                pass
            self._sse_response = None

        if self._owns_session and self._session is not None:
            try:
                await self._session.close()
            except Exception:
                # Expected-failure cleanup (zero-tolerance Rule 3 carve-out):
                # a session that errors on close is already unusable.
                pass
            self._session = None


def _parse_sse_retry_field(value: str) -> Optional[int]:
    """Parse the value of an SSE ``retry:`` field into milliseconds.

    Per the SSE specification the reconnection-time value MUST consist only
    of ASCII digits; any other content causes the field to be ignored. A
    single leading space after the colon is stripped before parsing.

    Returns the integer number of milliseconds, or ``None`` when the value
    is empty or not a base-10 ASCII-digit run.
    """
    stripped = value.lstrip()
    if stripped and all(ch in "0123456789" for ch in stripped):
        return int(stripped)
    return None


def _strip_sse_data_prefix(text: str) -> str:
    """If ``text`` looks like a single SSE ``data:`` event, strip the prefix.

    Accepts both forms:

    - ``data: {"jsonrpc": ...}\\n\\n``  → strips ``data:`` + whitespace.
    - ``{"jsonrpc": ...}``             → returned unchanged.

    Multi-line SSE events (multiple ``data:`` lines) are joined with
    newlines, matching the SSE spec's concatenation rule.
    """
    trimmed = text.strip()
    if not trimmed:
        return trimmed

    # Plain JSON path: starts with `{` or `[`.
    if trimmed[0] in "{[":
        return trimmed

    if not trimmed.startswith("data:"):
        return trimmed

    data_lines: list[str] = []
    for raw_line in trimmed.splitlines():
        line = raw_line.rstrip("\r\n")
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            data_lines.append(line[len("data:") :].lstrip())
        elif line == "":
            break
    return "\n".join(data_lines)


__all__ = ["SseTransport"]
