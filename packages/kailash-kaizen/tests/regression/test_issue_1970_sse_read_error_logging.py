"""Regression — the SSE read-error path LOGS, it does not ``print`` (#1970 follow-up).

``HTTPTransport._read_messages_impl`` swallows ``aiohttp.ClientError`` and
returns, ending the caller's message stream. Two things must hold on that path:

1. **It must go through the module logger, not ``print``.** ``print`` to stderr
   is unstructured, unroutable and uncorrelated — it carries no level, no
   fields, cannot be filtered or shipped to an aggregator, and disappears on
   restart (``rules/observability.md`` MUST Rule 1). This module already binds a
   logger at module scope and uses it elsewhere, so the ``print`` was an
   outlier, not a missing-logger problem.

2. **It must be sanitized.** aiohttp embeds the request URL in its exception
   text, and the control ``base_url`` can carry userinfo or a query-string
   token — so the raw exception is a credential-bearing surface
   (``rules/security.md`` § "No secrets in logs").

Tier 1: the aiohttp session seam is replaced with one that raises. No network.
"""

from __future__ import annotations

import logging

import aiohttp
import pytest

pytestmark = pytest.mark.regression

# Synthetic credential. NOT a real secret — shaped to match a
# ``_CREDENTIAL_PATTERNS`` entry in ``kaizen.nodes.ai.error_sanitizer``.
FAKE_TOKEN = "sk-proj-AAAABBBBCCCCDDDDEEEEFFFF1234"
RAW_SSE_ERROR = (
    f"Cannot connect to host ctl.internal:443 "
    f"(url=https://svc:{FAKE_TOKEN}@ctl.internal/stream)"
)


class _RaisingSession:
    """Minimal stand-in for ``aiohttp.ClientSession``.

    Not a ``MagicMock``: a mock auto-satisfies every attribute the read path
    touches, so a test built on one keeps passing against a path that no longer
    routes through the branch under test.
    """

    def get(self, url):  # noqa: D102 - matches aiohttp's sync-call/async-ctx shape
        raise aiohttp.ClientError(RAW_SSE_ERROR)


async def _drain(transport) -> list[str]:
    return [message async for message in transport.read_messages()]


@pytest.fixture
def connected_transport():
    from kaizen.core.autonomy.control.transports.http import HTTPTransport

    transport = HTTPTransport(base_url="https://ctl.internal")
    transport._session = _RaisingSession()
    transport._connected = True
    return transport


@pytest.mark.asyncio
async def test_sse_read_error_is_logged_not_printed(
    connected_transport, caplog, capsys
):
    """The handler emits an ERROR log record and writes nothing to stdout/stderr."""
    with caplog.at_level(
        logging.ERROR, logger="kaizen.core.autonomy.control.transports.http"
    ):
        assert await _drain(connected_transport) == []

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert errors, (
        "the SSE read-error path emitted no ERROR log record — it either still "
        "uses print() or swallows the failure silently"
    )

    captured = capsys.readouterr()
    assert RAW_SSE_ERROR not in captured.err and RAW_SSE_ERROR not in captured.out, (
        "the SSE read error reached stdout/stderr directly. print() is BLOCKED "
        "in production code (rules/observability.md MUST Rule 1); use the "
        "module logger so the record can be levelled, filtered and shipped.\n"
        f"  stderr: {captured.err!r}\n  stdout: {captured.out!r}"
    )


@pytest.mark.asyncio
async def test_sse_read_error_log_is_credential_scrubbed(connected_transport, caplog):
    """aiohttp embeds the URL; the control base_url can carry a token."""
    with caplog.at_level(
        logging.ERROR, logger="kaizen.core.autonomy.control.transports.http"
    ):
        await _drain(connected_transport)

    rendered = "\n".join(r.getMessage() for r in caplog.records)

    assert FAKE_TOKEN not in rendered, (
        "raw credential leaked into the SSE read-error log record.\n"
        f"  record: {rendered!r}"
    )
    assert "[REDACTED]" in rendered, (
        "the log record carries neither the credential nor the sanitizer's "
        "[REDACTED] marker — the message was dropped rather than sanitized, so "
        "this test would pass vacuously against a handler that logs nothing "
        f"useful.\n  record: {rendered!r}"
    )


@pytest.mark.asyncio
async def test_sse_read_error_terminates_the_stream_cleanly(connected_transport):
    """The documented contract: log and return, never propagate to the caller."""
    assert await _drain(connected_transport) == []
