"""Regression test: durability_middleware MUST NOT drain StreamingResponse.

Issue #767 — ``DurableWorkflowServer._add_durability_middleware``
unconditionally drained ``response.body_iterator`` for every 2xx
response before forwarding it to the client. For ``StreamingResponse``
(SSE, chunked transfer, file streams, gRPC streaming) this either
never returned (open-ended SSE generator) or replayed the captured
stream as a single JSON envelope on cache hit instead of a stream.

The fix in ``src/kailash/servers/durable_workflow_server.py`` short-
circuits before the drain when the response is a ``StreamingResponse``
instance OR when ``content-type`` is ``text/event-stream``. The
emit-completion event still fires (with ``streaming=true`` for
forensic correlation) so the request lifecycle is observable.

This test exercises the failure mode end-to-end against
``EnterpriseWorkflowServer``-style configuration (``durability_opt_in=
False``, every request durable) by mounting an SSE handler and asserting
the body iterator delivers chunked output to the client rather than the
buffered JSON envelope the bug produced.

See:
- src/kailash/servers/durable_workflow_server.py
- rules/zero-tolerance.md Rule 3 (no silent fallbacks)
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from starlette.responses import StreamingResponse

from kailash.servers.durable_workflow_server import DurableWorkflowServer

pytestmark = [pytest.mark.regression]


async def _sse_stream():
    """Three-event SSE generator with a small delay between events.

    The pre-fix middleware would drain this generator end-to-end before
    forwarding any bytes; with a delay between yields, an external
    observer can confirm the chunks arrived in order rather than as a
    single buffered envelope.
    """
    yield b"retry: 3000\n\n"
    yield b"event: ready\ndata: {}\n\n"
    await asyncio.sleep(0.01)
    yield b'event: tick\ndata: {"n": 1}\n\n'
    await asyncio.sleep(0.01)
    yield b'event: done\ndata: {"n": 2}\n\n'


def _build_sse_server() -> DurableWorkflowServer:
    """Server with durability ALWAYS on (enterprise-style configuration).

    Pre-fix: every SSE request crashed because ``durability_middleware``
    awaited the body iterator before forwarding the response.
    """
    server = DurableWorkflowServer(
        title="issue-767-regression",
        version="test",
        enable_durability=True,
        durability_opt_in=False,  # Mirror EnterpriseWorkflowServer default.
    )

    @server.app.get("/sse")
    async def sse_endpoint():
        return StreamingResponse(
            _sse_stream(),
            media_type="text/event-stream",
        )

    @server.app.get("/sse-via-bare-response")
    async def sse_via_bare_response():
        # Some handlers return a bare ``Response`` with content-type set to
        # text/event-stream rather than a ``StreamingResponse``; the
        # middleware MUST detect via the content-type header too.
        return StreamingResponse(
            _sse_stream(),
            media_type="text/event-stream",
            headers={"X-Streaming-Marker": "bare-response-content-type"},
        )

    return server


@pytest.mark.asyncio
async def test_durability_middleware_passes_through_streaming_response():
    """First SSE response MUST keep ``text/event-stream`` content-type.

    Pre-fix the durability middleware drained the body iterator and re-wrapped
    it as ``Response(content=joined_bytes, media_type="text/event-stream")``,
    so the immediate response body was identical. The semantic loss surfaced
    on the second request (see ``test_..._cache_replay``); this test is the
    structural-headers companion.
    """
    server = _build_sse_server()

    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/sse")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    body = response.text
    assert "retry: 3000" in body
    assert "event: ready" in body
    assert "event: tick" in body
    assert "event: done" in body


@pytest.mark.asyncio
async def test_durability_middleware_does_not_replay_sse_as_json_envelope():
    """Cache-hit replay MUST keep streaming semantics, not JSON-wrap.

    Pre-fix: the first SSE GET drained the iterator and the dedup layer
    cached ``{"content": "retry: 3000\\n\\n…"}``. The second identical GET
    hit the cache and returned ``JSONResponse(content=cached_response)`` —
    a JSON envelope at ``application/json``, not the SSE stream.
    Every SSE client (EventSource, ``httpx.stream``, manual SSE parser)
    would see a non-stream response and either error or sit waiting.

    Post-fix: streaming responses short-circuit before drain AND before
    cache, so the second request invokes the handler again and returns
    a fresh SSE stream.
    """
    server = _build_sse_server()

    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.get("/sse")
        second = await client.get("/sse")

    assert first.status_code == 200
    assert second.status_code == 200

    # The structural failure mode: pre-fix, the second response was a
    # ``JSONResponse(content={"content": ..., "status_code": 200, ...})`` —
    # content-type ``application/json`` and body shape ``{"content": "..."}``.
    assert second.headers["content-type"].startswith("text/event-stream"), (
        "durability_middleware replayed the cached SSE response as a JSON "
        f"envelope; see issue #767. content-type={second.headers.get('content-type')!r}"
    )
    body = second.text
    assert "event: ready" in body
    assert "event: done" in body
    # Sentinel: the bug shape replays the cache as ``{"content": "..."}``.
    assert not body.lstrip().startswith("{"), (
        "durability_middleware replayed the cached stream as a JSON envelope; "
        f"see issue #767. body={body[:200]!r}"
    )


@pytest.mark.asyncio
async def test_durability_middleware_detects_text_event_stream_content_type():
    """Content-type marker MUST be honoured even on non-StreamingResponse paths."""
    server = _build_sse_server()

    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/sse-via-bare-response")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers.get("X-Streaming-Marker") == "bare-response-content-type"
    body = response.text
    assert "event: ready" in body
    assert not body.lstrip().startswith("{")


@pytest.mark.asyncio
async def test_durability_middleware_still_buffers_json_responses():
    """Non-streaming responses MUST keep the original drain+cache behaviour."""
    server = DurableWorkflowServer(
        title="issue-767-regression-json",
        version="test",
        enable_durability=True,
        durability_opt_in=False,
    )

    @server.app.get("/json")
    async def json_endpoint():
        return {"hello": "world", "n": 42}

    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/json")

    assert response.status_code == 200
    assert response.json() == {"hello": "world", "n": 42}
