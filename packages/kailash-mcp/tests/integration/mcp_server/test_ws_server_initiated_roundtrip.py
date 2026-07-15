# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Real-WebSocket end-to-end tests for #1712 W6 FINDING 2 — the single-client
server-initiated round-trip must NOT deadlock.

These tests stand up a REAL ``WebSocketServerTransport`` bound to REAL
``MCPServer`` handlers on a loopback port (``websockets.serve``) and connect ONE
REAL ``websockets`` client. The client is BOTH the requester AND the responder
on the SAME socket — exactly the ``target == requester`` case F4 made the normal
one. The client's inbound reply to the server-initiated request arrives as a NEW
frame on the same connection, so ``handle_client`` MUST keep reading the socket
while a handler awaits that reply.

This DRIVES the actual ``handle_client`` loop end to end — it is NOT a
task-injected reply on a side channel (the exact bypass FINDING 2 calls out). A
sequential read loop would never read the reply frame while the sampling /
elicitation handler is mid-await, so the handler would block until its timeout
(-32811 for sampling); the concurrent-dispatch fix reads it immediately.
"""

import asyncio
import json
import socket

import pytest
import websockets

from kailash_mcp.server import MCPServer
from kailash_mcp.transports.transports import WebSocketServerTransport


def _free_port() -> int:
    """Return an unused loopback TCP port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def _serve(server: MCPServer) -> WebSocketServerTransport:
    """Bind a real WS transport to the server's handlers on a free port."""
    port = _free_port()
    transport = WebSocketServerTransport(
        host="127.0.0.1",
        port=port,
        message_handler=server._handle_websocket_message,
        disconnect_handler=server._on_ws_disconnect,
    )
    server._transport = transport
    await transport.connect()
    # Bind the transport's send-callable to the elicitation system exactly as the
    # server's own WS-startup path does, so elicitation/create dispatches over
    # this real connection.
    server._bind_elicitation_transport()
    transport._test_port = port  # type: ignore[attr-defined]
    return transport


@pytest.mark.integration
@pytest.mark.asyncio
async def test_single_client_sampling_roundtrip_no_deadlock():
    """One real client sends sampling/createMessage and REPLIES to the
    server-initiated sampling/createMessage on the SAME socket; the requester's
    original request receives the model completion within a short timeout — NOT
    a -32811 sampling timeout (FINDING 2 — WS single-client deadlock)."""
    server = MCPServer("ws-roundtrip-sampling", enable_cache=False, enable_metrics=False)
    server.set_sampling_approver(lambda ctx: True)
    # Short timeout: a REGRESSED sequential loop would surface as a fast -32811,
    # not a 30s hang — the test fails loud within seconds either way.
    server._sampling_timeout = 4.0

    transport = await _serve(server)
    port = transport._test_port  # type: ignore[attr-defined]
    try:
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            # (a) register + advertise sampling via initialize.
            await ws.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": "init",
                        "method": "initialize",
                        "params": {
                            "capabilities": {"sampling": {}},
                            "clientInfo": {"name": "t", "version": "1"},
                        },
                    }
                )
            )
            init = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            assert init["id"] == "init"

            completion = {
                "role": "assistant",
                "content": {"type": "text", "text": "hello from the client"},
                "model": "test-model",
            }
            final: dict = {}

            async def client_loop():
                # (b) send an inbound sampling/createMessage (this client is the
                # requester).
                await ws.send(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": "req-1",
                            "method": "sampling/createMessage",
                            "params": {
                                "messages": [{"role": "user", "content": "hi"}]
                            },
                        }
                    )
                )
                # (c) concurrently read inbound frames and REPLY to the
                # server-initiated sampling/createMessage on the SAME socket.
                while True:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=6))
                    if msg.get("method") == "sampling/createMessage":
                        await ws.send(
                            json.dumps(
                                {
                                    "jsonrpc": "2.0",
                                    "id": msg["id"],
                                    "result": completion,
                                }
                            )
                        )
                        continue
                    if msg.get("id") == "req-1":
                        final.update(msg)
                        return

            await asyncio.wait_for(client_loop(), timeout=6)

            assert "error" not in final, f"expected completion, got error: {final}"
            assert final["result"] == completion
    finally:
        await transport.disconnect()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_single_client_elicitation_roundtrip_no_deadlock():
    """A tool invoked by the client awaits elicitation input; the SAME client
    replies to the server-initiated elicitation/create on the SAME socket and the
    tools/call completes (FINDING 2 concurrent dispatch + FINDING 3
    client-scoped elicitation dispatched to the invoking client)."""
    server = MCPServer(
        "ws-roundtrip-elicitation", enable_cache=False, enable_metrics=False
    )

    @server.tool()
    async def ask_name() -> dict:
        answer = await server.elicitation_system.request_input(
            "your name?",
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            timeout=4.0,
        )
        return {"greeted": answer["name"]}

    transport = await _serve(server)
    port = transport._test_port  # type: ignore[attr-defined]
    try:
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await ws.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": "init",
                        "method": "initialize",
                        "params": {
                            "capabilities": {"elicitation": {"modes": ["form"]}},
                            "clientInfo": {"name": "t", "version": "1"},
                        },
                    }
                )
            )
            init = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            assert init["id"] == "init"

            final: dict = {}

            async def client_loop():
                await ws.send(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": "call-1",
                            "method": "tools/call",
                            "params": {"name": "ask_name", "arguments": {}},
                        }
                    )
                )
                while True:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=6))
                    if msg.get("method") == "elicitation/create":
                        await ws.send(
                            json.dumps(
                                {
                                    "jsonrpc": "2.0",
                                    "id": msg["id"],
                                    "result": {
                                        "action": "accept",
                                        "content": {"name": "Ada"},
                                    },
                                }
                            )
                        )
                        continue
                    if msg.get("id") == "call-1":
                        final.update(msg)
                        return

            await asyncio.wait_for(client_loop(), timeout=6)

            assert final.get("id") == "call-1"
            assert "error" not in final, f"expected tool result, got error: {final}"
            assert final["result"].get("isError") is not True
            # The collected name round-tripped through the tool result.
            assert "Ada" in json.dumps(final["result"])
    finally:
        await transport.disconnect()
