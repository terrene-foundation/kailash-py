# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 integration tests for MCP transport primitives — issue #600.

NO mocking per rules/testing.md § 3-Tier Testing — every transport is
exercised against real infrastructure (real subprocess for stdio, real
aiohttp test server for sse/http).
"""

from __future__ import annotations

import asyncio
import json
import sys
import textwrap

import aiohttp
import pytest
from aiohttp import web

from kailash.channels.mcp import (
    HttpTransport,
    SseTransport,
    StdioTransport,
    TransportError,
)


pytestmark = pytest.mark.integration


# ----- StdioTransport against a real subprocess ----------------------------


_ECHO_SERVER_SOURCE = textwrap.dedent(
    """\
    import sys

    def _read_message(stream):
        # Read LSP-style framed message: Content-Length: N\\r\\n\\r\\n<body>
        header_bytes = b""
        while not header_bytes.endswith(b"\\r\\n\\r\\n"):
            byte = stream.buffer.read(1)
            if not byte:
                return None
            header_bytes += byte
        header = header_bytes.decode("utf-8")
        for line in header.split("\\r\\n"):
            if line.lower().startswith("content-length:"):
                length = int(line.split(":", 1)[1].strip())
                break
        else:
            return None
        return stream.buffer.read(length).decode("utf-8")

    def _write_message(stream, body):
        encoded = body.encode("utf-8")
        stream.buffer.write(f"Content-Length: {len(encoded)}\\r\\n\\r\\n".encode("ascii"))
        stream.buffer.write(encoded)
        stream.buffer.flush()

    while True:
        msg = _read_message(sys.stdin)
        if msg is None:
            break
        _write_message(sys.stdout, msg)  # echo
    """
)


class TestStdioTransportReal:
    @pytest.mark.asyncio
    async def test_send_receive_echo(self, tmp_path) -> None:
        echo_script = tmp_path / "echo_server.py"
        echo_script.write_text(_ECHO_SERVER_SOURCE)
        transport = await StdioTransport.spawn(
            command=sys.executable,
            args=[str(echo_script)],
            allowed=[sys.executable, "python3", "python"],
        )
        try:
            request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"})
            response = await transport.send(request)
            # Echo server returns whatever we sent.
            assert json.loads(response) == json.loads(request)
        finally:
            await transport.close()


# ----- HttpTransport against a real aiohttp server -------------------------


@pytest.fixture
async def http_echo_server(aiohttp_unused_port):
    port = aiohttp_unused_port()

    async def handler(request: web.Request) -> web.Response:
        body = await request.text()
        # Pretend to be an MCP server: echo the request payload.
        return web.json_response(json.loads(body))

    app = web.Application()
    app.router.add_post("/mcp", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        await runner.cleanup()


class TestHttpTransportReal:
    @pytest.mark.asyncio
    async def test_send_round_trip(self, http_echo_server) -> None:
        transport = HttpTransport(http_echo_server, allow_private=True)
        try:
            request = json.dumps({"jsonrpc": "2.0", "id": 7, "method": "echo"})
            response = await transport.send(request)
            assert json.loads(response) == json.loads(request)
        finally:
            await transport.close()

    @pytest.mark.asyncio
    async def test_receive_raises(self, http_echo_server) -> None:
        transport = HttpTransport(http_echo_server, allow_private=True)
        try:
            with pytest.raises(NotImplementedError):
                await transport.receive()
        finally:
            await transport.close()


# ----- SseTransport against a real aiohttp server -------------------------


@pytest.fixture
async def sse_server(aiohttp_unused_port):
    port = aiohttp_unused_port()

    async def message_handler(request: web.Request) -> web.Response:
        body = await request.text()
        return web.json_response(json.loads(body))

    async def sse_handler(request: web.Request) -> web.StreamResponse:
        resp = web.StreamResponse(
            status=200,
            headers={"Content-Type": "text/event-stream"},
        )
        await resp.prepare(request)
        await resp.write(
            b"data: " + json.dumps({"event": "hello"}).encode("utf-8") + b"\n\n"
        )
        return resp

    app = web.Application()
    app.router.add_post("/message", message_handler)
    app.router.add_get("/sse", sse_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        await runner.cleanup()


class TestSseTransportReal:
    @pytest.mark.asyncio
    async def test_send_receive_echo(self, sse_server) -> None:
        transport = SseTransport(sse_server, allow_private=True)
        try:
            request = json.dumps({"jsonrpc": "2.0", "id": 42, "method": "echo"})
            response = await transport.send(request)
            assert json.loads(response) == json.loads(request)
        finally:
            await transport.close()
