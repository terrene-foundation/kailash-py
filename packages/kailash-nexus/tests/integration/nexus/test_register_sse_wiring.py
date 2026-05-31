# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 wiring tests for Nexus.register_sse (issue #1174 AC 5).

Drives a REAL Nexus HTTP gateway via Starlette's ``TestClient`` — the full
ASGI stack (route → StreamingResponse → bounded-queue producer/consumer →
client) executes end to end. NO MOCKING.

Covers (spec §325 test contract row 5 + the 6 MUSTs):
- ``on_subscribe`` yields N events; the client reads N ``data:`` frames.
- keepalive comment fires on idleness.
- client disconnect → the ``on_subscribe`` iterator is cancelled gracefully
  (cleanup runs, no leaked subscription).
- MUST 1: a raising ``Depends`` closes with HTTP 401 + JSON body BEFORE the
  SSE handshake — never a partial ``text/event-stream``.
- MUST 3: an oversized event is dropped with an ``EVENT_TOO_LARGE`` frame and
  the stream CONTINUES.
- canonical SSE headers (``text/event-stream`` / ``no-cache`` /
  ``X-Accel-Buffering: no``).
"""

import asyncio
import socket

import pytest
from fastapi.testclient import TestClient

from nexus import Nexus
from nexus.extractors import Depends, NexusHandlerError, Request


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _client_for(app: Nexus) -> TestClient:
    """Start the HTTP transport (flushing the queued SSE endpoint) + client."""
    asyncio.run(app._http_transport.start(app._registry))
    assert app.fastapi_app is not None
    return TestClient(app.fastapi_app, raise_server_exceptions=False)


def _parse_frames(raw: str):
    """Split an SSE stream into ``data:`` payloads and ``error`` codes."""
    data_frames = []
    error_codes = []
    keepalives = 0
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        is_error = any(line.strip() == "event: error" for line in lines)
        for line in lines:
            if line.startswith(":"):
                keepalives += 1
            elif line.startswith("data:"):
                payload = line[len("data:") :].strip()
                if is_error:
                    import json

                    error_codes.append(json.loads(payload).get("code"))
                else:
                    data_frames.append(payload)
    return data_frames, error_codes, keepalives


@pytest.mark.integration
def test_register_sse_yields_events_and_frames():
    """on_subscribe yields 3 events; client reads 3 data frames (AC 5)."""
    app = Nexus(api_port=_free_port(), auto_discovery=False, enable_auth=False)

    async def on_subscribe(request):
        for i in range(3):
            yield {"tick": i}

    app.register_sse("/feed", on_subscribe)
    client = _client_for(app)

    with client.stream("GET", "/feed") as resp:
        assert resp.status_code == 200, resp.status_code
        ct = resp.headers.get("content-type", "")
        assert "text/event-stream" in ct, ct
        assert "no-cache" in resp.headers.get("cache-control", "")
        assert resp.headers.get("x-accel-buffering") == "no"
        resp.read()
        raw = resp.text

    data_frames, errors, _ = _parse_frames(raw)
    assert errors == [], errors
    import json

    parsed = [json.loads(d) for d in data_frames]
    assert parsed == [{"tick": 0}, {"tick": 1}, {"tick": 2}], parsed


@pytest.mark.integration
def test_register_sse_keepalive_on_idle():
    """A keepalive comment fires when on_subscribe idles past the interval."""
    app = Nexus(api_port=_free_port(), auto_discovery=False, enable_auth=False)

    async def on_subscribe(request):
        yield {"first": True}
        # Idle longer than keepalive_interval (1s) so ≥1 keepalive comment is
        # forced, then emit one more event to terminate deterministically.
        await asyncio.sleep(1.2)
        yield {"second": True}

    app.register_sse("/idle", on_subscribe, keepalive_interval=1)
    client = _client_for(app)

    with client.stream("GET", "/idle") as resp:
        assert resp.status_code == 200, resp.status_code
        resp.read()
        raw = resp.text

    data_frames, errors, keepalives = _parse_frames(raw)
    assert errors == [], errors
    assert len(data_frames) == 2, data_frames
    # The 1.2s idle gap past the 1s interval forces ≥1 ": keepalive" comment.
    assert keepalives >= 1, raw


@pytest.mark.integration
async def test_register_sse_client_disconnect_cancels_iterator():
    """Client disconnect cancels on_subscribe; the finally-cleanup runs (MUST 6).

    Drives the production stream generator (``nexus.sse._sse_stream``) directly
    and calls ``.aclose()`` on it after reading two frames — which is EXACTLY
    what Starlette's ``StreamingResponse`` does to the body iterator on client
    disconnect. Asserts the user ``on_subscribe`` generator's ``finally`` ran
    (resources released) and that the internal producer task was cancelled.
    Driving the generator directly is deterministic (no flaky in-process ASGI
    disconnect detection) while exercising the real cancellation codepath.
    """
    from nexus.sse import _sse_stream

    cleanup = {"ran": False, "last_n": -1}

    async def on_subscribe(request):
        try:
            i = 0
            while True:  # infinite — only a disconnect ends it
                yield {"n": i}
                cleanup["last_n"] = i
                i += 1
                await asyncio.sleep(0.01)
        finally:
            cleanup["ran"] = True

    gen = _sse_stream(
        request=None,
        on_subscribe=on_subscribe,
        keepalive_interval=15,
        max_queue_depth=1000,
        max_event_bytes=65_536,
        slow_consumer_timeout=30.0,
        path="/infinite",
    )

    # Read two data frames, then disconnect (aclose the body iterator).
    frames = []
    async for frame in gen:
        if frame.startswith("data:"):
            frames.append(frame)
        if len(frames) >= 2:
            break
    assert len(frames) == 2, frames

    # Simulate the disconnect: Starlette aclose()s the response body iterator.
    await gen.aclose()

    # The user generator's finally must have run (MUST 6 graceful cleanup), and
    # we stopped well before any natural end (it was infinite).
    for _ in range(200):
        if cleanup["ran"]:
            break
        await asyncio.sleep(0.01)
    assert cleanup["ran"] is True, "on_subscribe finally-cleanup did not run"
    assert cleanup["last_n"] >= 1, cleanup["last_n"]


@pytest.mark.integration
def test_register_sse_raising_dependency_closes_401_before_handshake():
    """MUST 1: a raising Depends yields 401 + JSON, NOT a partial stream."""
    app = Nexus(api_port=_free_port(), auto_discovery=False, enable_auth=False)

    def require_token(request: Request):
        if request.headers.get("authorization") != "Bearer good":
            raise NexusHandlerError(
                status_code=401, body={"error": "unauthorized", "code": "UNAUTHORIZED"}
            )
        return True

    async def on_subscribe(request):
        yield {"secret": "data"}

    app.register_sse("/guarded", on_subscribe, dependencies=[Depends(require_token)])
    client = _client_for(app)

    # Unauthenticated → 401 + JSON, never an event-stream body.
    resp = client.get("/guarded")
    assert resp.status_code == 401, resp.text
    assert "text/event-stream" not in resp.headers.get("content-type", "")
    body = resp.json()
    assert body.get("code") == "UNAUTHORIZED", body

    # Authenticated → the stream flows.
    with client.stream(
        "GET", "/guarded", headers={"Authorization": "Bearer good"}
    ) as r:
        assert r.status_code == 200, r.status_code
        assert "text/event-stream" in r.headers.get("content-type", "")
        r.read()
        data_frames, errors, _ = _parse_frames(r.text)
    assert errors == [], errors
    import json

    assert [json.loads(d) for d in data_frames] == [{"secret": "data"}]


@pytest.mark.integration
def test_register_sse_rate_limit_exceeded_returns_429_before_handshake():
    """MUST 5: per-client-IP rate limit on SUBSCRIBE → 429 before the stream.

    Nexus(rate_limit=2) caps the SSE subscribe path at 2 req/min per client IP.
    The TestClient is a single client IP, so the 3rd subscribe in the same
    minute MUST return HTTP 429 with the canonical {error,code} envelope BEFORE
    any text/event-stream handshake (issue #1174 AC 5 MUST 5).
    """
    app = Nexus(
        api_port=_free_port(),
        auto_discovery=False,
        enable_auth=False,
        rate_limit=2,
    )

    async def on_subscribe(request):
        yield {"ok": True}

    app.register_sse("/limited", on_subscribe)
    client = _client_for(app)

    # First two subscribes are allowed (drain each so the stream completes).
    for _ in range(2):
        with client.stream("GET", "/limited") as resp:
            assert resp.status_code == 200, resp.status_code
            assert "text/event-stream" in resp.headers.get("content-type", "")
            resp.read()

    # Third subscribe in the same minute exceeds rate_limit=2 → 429 before the
    # handshake, with the canonical envelope, NOT a partial event-stream.
    resp = client.get("/limited")
    assert resp.status_code == 429, resp.text
    assert "text/event-stream" not in resp.headers.get("content-type", "")
    body = resp.json()
    assert body.get("code") == "RATE_LIMITED", body
    assert "error" in body, body


@pytest.mark.integration
def test_register_sse_no_rate_limit_when_unset():
    """MUST 5 default: rate_limit=None disables the limit (preserves semantics)."""
    app = Nexus(
        api_port=_free_port(),
        auto_discovery=False,
        enable_auth=False,
        rate_limit=None,
    )

    async def on_subscribe(request):
        yield {"ok": True}

    app.register_sse("/unlimited", on_subscribe)
    client = _client_for(app)

    # Many subscribes in the same minute — none is rate-limited.
    for _ in range(5):
        with client.stream("GET", "/unlimited") as resp:
            assert resp.status_code == 200, resp.status_code
            resp.read()


@pytest.mark.integration
async def test_register_sse_slow_consumer_closes_stream_and_releases_producer():
    """MUST 4: a slow consumer that cannot drain within slow_consumer_timeout
    closes the stream; the finally cancels the producer + releases state.

    Drives the production stream generator (``nexus.sse._sse_stream``) directly
    with a SHORT slow_consumer_timeout and a producer that idles forever after
    its first event. The consumer reads the first frame, then stops pulling
    (simulating a wedged transport); when no flush succeeds within the timeout
    the generator returns, and its ``finally`` cancels the producer task so the
    user ``on_subscribe`` generator's ``finally`` (resource release) runs.
    """
    import time

    from nexus.sse import _sse_stream

    cleanup = {"ran": False}

    async def on_subscribe(request):
        try:
            yield {"first": True}
            # Idle forever after the first event: the consumer's slow-consumer
            # deadline (not a producer event) is what must terminate the stream.
            await asyncio.sleep(3600)
        finally:
            cleanup["ran"] = True

    gen = _sse_stream(
        request=None,
        on_subscribe=on_subscribe,
        keepalive_interval=0,  # disable keepalive so only slow-consumer fires
        max_queue_depth=1000,
        max_event_bytes=65_536,
        slow_consumer_timeout=0.3,
        path="/slow",
    )

    started = time.monotonic()
    frames = []
    async for frame in gen:
        if frame.startswith("data:"):
            frames.append(frame)
        # Read the first data frame, then stop pulling promptly so the
        # generator hits its slow-consumer deadline on the next iteration.
        if frames:
            break

    assert len(frames) == 1, frames

    # Resume iterating: with no further events and keepalive disabled, the
    # generator MUST return within ~slow_consumer_timeout (slow-consumer close).
    async for _ in gen:
        pass  # drains until the generator returns (terminal)
    elapsed = time.monotonic() - started

    # The stream closed on the slow-consumer deadline, not after the 3600s idle.
    assert elapsed < 5.0, f"stream did not close on slow-consumer timeout ({elapsed}s)"

    # The generator's finally cancelled the producer, so on_subscribe's finally
    # (resource release) ran — producer state is released (MUST 4).
    for _ in range(200):
        if cleanup["ran"]:
            break
        await asyncio.sleep(0.01)
    assert cleanup["ran"] is True, "producer not released on slow-consumer close"


@pytest.mark.integration
def test_register_sse_oversized_event_dropped_then_continues():
    """MUST 3: an oversized event yields EVENT_TOO_LARGE then the stream goes on."""
    app = Nexus(api_port=_free_port(), auto_discovery=False, enable_auth=False)

    async def on_subscribe(request):
        yield {"small": 1}
        yield {"big": "x" * 5000}  # exceeds the tiny cap below
        yield {"small": 2}

    app.register_sse("/sized", on_subscribe, max_event_bytes=64)
    client = _client_for(app)

    with client.stream("GET", "/sized") as resp:
        assert resp.status_code == 200, resp.status_code
        resp.read()
        data_frames, errors, _ = _parse_frames(resp.text)

    import json

    # The oversized event is dropped; the two small events survive.
    assert [json.loads(d) for d in data_frames] == [
        {"small": 1},
        {"small": 2},
    ], data_frames
    assert errors == ["EVENT_TOO_LARGE"], errors
