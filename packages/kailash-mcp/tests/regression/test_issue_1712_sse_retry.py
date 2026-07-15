# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression test for #1712 - SSE ``retry:`` reconnection field.

The native ``SseTransport`` (``kailash.channels.mcp.sse``) previously
discarded the SSE ``retry:`` field ("Any other field (event:, id:, retry:)
is ignored"). MCP requires clients to respect the SSE ``retry:``
reconnection time. These behavioral pins (call the parser / feed the stream,
assert the captured value - never source-grep, per ``rules/testing.md``)
verify the field is now parsed and captured.

Real parsing only - no mocking. The transport's event reader is driven with
a real async iterator of real ``bytes`` SSE lines (real input to real
parsing code), and the pure field parser is called directly.
"""

import pytest

from kailash.channels.mcp.sse import (
    MAX_RECONNECT_MS,
    SseTransport,
    _parse_sse_retry_field,
)


# ---------------------------------------------------------------------------
# 1. Pure field parser - captures ASCII-digit milliseconds, rejects the rest
# ---------------------------------------------------------------------------


def test_parse_retry_field_captures_millisecond_value():
    """A well-formed ``retry:`` value is parsed to an int (milliseconds)."""
    # The value passed to the parser is the text AFTER "retry:", exactly as
    # the transport slices it. A single leading space is stripped.
    assert _parse_sse_retry_field(" 5000") == 5000
    assert _parse_sse_retry_field("2500") == 2500
    assert _parse_sse_retry_field("0") == 0


def test_parse_retry_field_rejects_non_digit_values():
    """Per the SSE spec, non-ASCII-digit values cause the field to be ignored."""
    assert _parse_sse_retry_field("") is None
    assert _parse_sse_retry_field("   ") is None
    assert _parse_sse_retry_field("5000ms") is None
    assert _parse_sse_retry_field("abc") is None
    assert _parse_sse_retry_field("-1") is None
    assert _parse_sse_retry_field("1.5") is None


# ---------------------------------------------------------------------------
# 2. Transport captures the retry field off a real SSE line stream
# ---------------------------------------------------------------------------


async def _byte_lines(*lines: str):
    """A real async iterator yielding real ``bytes`` SSE lines.

    This is a genuine async generator over real input data fed to the real
    parser in :meth:`SseTransport._read_event` - not a mock of any behavior.
    """
    for line in lines:
        yield (line + "\r\n").encode("utf-8")


@pytest.mark.regression
@pytest.mark.asyncio
async def test_sse_transport_captures_retry_field():
    """``_read_event`` records the server's ``retry:`` into ``reconnect_delay_ms``."""
    transport = SseTransport("https://mcp.example.com", allow_private=False)

    # Before any event, no server reconnect delay has been observed.
    assert transport.reconnect_delay_ms is None

    event = await transport._read_event(
        _byte_lines(
            "retry: 5000",
            'data: {"jsonrpc": "2.0", "id": 1, "result": {}}',
            "",  # blank line terminates the event
        )
    )

    # The data payload is returned to the caller...
    assert event == '{"jsonrpc": "2.0", "id": 1, "result": {}}'
    # ...and the retry reconnection delay is now captured (previously discarded).
    assert transport.reconnect_delay_ms == 5000


@pytest.mark.regression
@pytest.mark.asyncio
async def test_sse_transport_ignores_malformed_retry_field():
    """A non-digit ``retry:`` value leaves ``reconnect_delay_ms`` unset."""
    transport = SseTransport("https://mcp.example.com")

    event = await transport._read_event(
        _byte_lines(
            "retry: not-a-number",
            'data: {"jsonrpc": "2.0"}',
            "",
        )
    )

    assert event == '{"jsonrpc": "2.0"}'
    assert transport.reconnect_delay_ms is None


# ---------------------------------------------------------------------------
# 3. Ceiling clamp (L1) — a hostile/huge retry cannot pin the client
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_sse_transport_clamps_retry_above_ceiling():
    """A ``retry:`` above ``MAX_RECONNECT_MS`` is clamped to the ceiling.

    Without the clamp a malicious/misconfigured server could send a huge
    ``retry:`` (e.g. one hour) and pin the client into an arbitrarily long
    reconnect wait — a DoS on the client's own reconnect path.
    """
    transport = SseTransport("https://mcp.example.com")

    # 3_600_000 ms == 1 hour, far above the 5-minute ceiling.
    huge = MAX_RECONNECT_MS * 12
    event = await transport._read_event(
        _byte_lines(
            f"retry: {huge}",
            'data: {"jsonrpc": "2.0"}',
            "",
        )
    )

    assert event == '{"jsonrpc": "2.0"}'
    # Stored value is clamped to the ceiling, never the server's huge value.
    assert transport.reconnect_delay_ms == MAX_RECONNECT_MS


@pytest.mark.regression
@pytest.mark.asyncio
async def test_sse_transport_retry_at_ceiling_passes_through():
    """A ``retry:`` exactly at the ceiling is stored unchanged."""
    transport = SseTransport("https://mcp.example.com")

    await transport._read_event(
        _byte_lines(f"retry: {MAX_RECONNECT_MS}", 'data: {"jsonrpc": "2.0"}', "")
    )

    assert transport.reconnect_delay_ms == MAX_RECONNECT_MS


@pytest.mark.regression
@pytest.mark.asyncio
async def test_sse_transport_normal_retry_passes_through_unclamped():
    """A normal in-range ``retry:`` is stored verbatim (clamp only bites above)."""
    transport = SseTransport("https://mcp.example.com")

    await transport._read_event(
        _byte_lines("retry: 5000", 'data: {"jsonrpc": "2.0"}', "")
    )

    assert transport.reconnect_delay_ms == 5000


@pytest.mark.regression
@pytest.mark.asyncio
async def test_sse_transport_negative_retry_leaves_default():
    """A negative ``retry:`` is rejected by the parser → the default stands.

    The parser only accepts an ASCII-digit run, so ``-1`` returns ``None`` and
    ``reconnect_delay_ms`` keeps its default (``None`` — no server-requested
    delay), rather than storing a nonsensical negative sleep.
    """
    transport = SseTransport("https://mcp.example.com")

    await transport._read_event(
        _byte_lines("retry: -1", 'data: {"jsonrpc": "2.0"}', "")
    )

    assert transport.reconnect_delay_ms is None
