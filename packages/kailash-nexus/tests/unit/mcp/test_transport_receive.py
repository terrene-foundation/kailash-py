"""
Tier 1 Unit Tests for Nexus WebSocketServerTransport.receive_message

Verifies that the WebSocketServerTransport correctly enqueues incoming
WebSocket messages and that receive_message() dequeues them in FIFO order.

Coverage:
- _message_queue initialised in __init__
- _handle_client enqueues parsed JSON messages
- receive_message returns queued messages in order
- receive_message blocks when queue is empty
- Multiple messages are delivered in FIFO order
- Message handler callback still fires alongside enqueueing
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nexus.mcp.transport import WebSocketServerTransport

# ============================================
# Fixtures
# ============================================


@pytest.fixture
def transport():
    """Create a WebSocketServerTransport with defaults."""
    return WebSocketServerTransport(host="127.0.0.1", port=3099)


@pytest.fixture
def transport_with_handler():
    """Create a transport with a message handler."""
    handler = AsyncMock(return_value={"type": "ack"})
    return WebSocketServerTransport(
        host="127.0.0.1", port=3099, message_handler=handler
    )


# ============================================
# Queue initialisation
# ============================================


def test_message_queue_initialised(transport):
    """_message_queue should be an asyncio.Queue created in __init__."""
    assert hasattr(transport, "_message_queue")
    assert isinstance(transport._message_queue, asyncio.Queue)
    assert transport._message_queue.empty()


# ============================================
# receive_message tests
# ============================================


@pytest.mark.asyncio
async def test_receive_message_returns_enqueued_message(transport):
    """receive_message should return a message that was put in the queue."""
    msg = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
    await transport._message_queue.put(msg)

    result = await transport.receive_message()

    assert result == msg
    assert transport._message_queue.empty()


@pytest.mark.asyncio
async def test_receive_message_fifo_order(transport):
    """Messages should be returned in FIFO order."""
    msgs = [
        {"id": 1, "method": "tools/list"},
        {"id": 2, "method": "tools/call"},
        {"id": 3, "method": "resources/list"},
    ]
    for m in msgs:
        await transport._message_queue.put(m)

    results = []
    for _ in msgs:
        results.append(await transport.receive_message())

    assert results == msgs


@pytest.mark.asyncio
async def test_receive_message_blocks_when_empty(transport):
    """receive_message should block until a message is available."""

    async def delayed_put():
        await asyncio.sleep(0.05)
        await transport._message_queue.put({"id": 42})

    asyncio.get_event_loop().create_task(delayed_put())

    result = await asyncio.wait_for(transport.receive_message(), timeout=2.0)

    assert result["id"] == 42


# ============================================
# _handle_client enqueue tests
# ============================================


def _make_fake_websocket(messages):
    """Create a fake WebSocket that yields pre-defined messages then closes."""
    ws = AsyncMock()
    ws.remote_address = ("127.0.0.1", 9999)
    ws.send = AsyncMock()

    async def async_iter():
        for m in messages:
            yield json.dumps(m)

    ws.__aiter__ = lambda self: async_iter()
    return ws


@pytest.mark.asyncio
async def test_handle_client_enqueues_messages(transport):
    """_handle_client should put each valid JSON message into _message_queue."""
    msgs = [
        {"jsonrpc": "2.0", "method": "tools/list", "id": 1},
        {"jsonrpc": "2.0", "method": "resources/read", "id": 2},
    ]
    ws = _make_fake_websocket(msgs)

    await transport._handle_client(ws, "/")

    assert transport._message_queue.qsize() == 2

    first = await transport.receive_message()
    assert first["method"] == "tools/list"
    assert "_client" in first

    second = await transport.receive_message()
    assert second["method"] == "resources/read"


@pytest.mark.asyncio
async def test_handle_client_still_calls_message_handler(transport_with_handler):
    """When a message_handler is set, it should still be called in addition to enqueueing."""
    t = transport_with_handler
    msgs = [{"jsonrpc": "2.0", "method": "ping", "id": 1}]
    ws = _make_fake_websocket(msgs)

    await t._handle_client(ws, "/")

    # Message should be enqueued
    assert t._message_queue.qsize() == 1

    # Handler should have been called
    t.message_handler.assert_awaited_once()
    handler_arg = t.message_handler.call_args[0][0]
    assert handler_arg["method"] == "ping"


@pytest.mark.asyncio
async def test_handle_client_invalid_json_not_enqueued(transport):
    """Invalid JSON messages should not be enqueued."""
    ws = AsyncMock()
    ws.remote_address = ("127.0.0.1", 9999)
    ws.send = AsyncMock()

    async def async_iter():
        yield "not valid json{"

    ws.__aiter__ = lambda self: async_iter()

    await transport._handle_client(ws, "/")

    assert transport._message_queue.empty()


@pytest.mark.asyncio
async def test_handle_client_adds_client_reference(transport):
    """Each enqueued message should have a _client key pointing to the WebSocket."""
    msgs = [{"id": 1}]
    ws = _make_fake_websocket(msgs)

    await transport._handle_client(ws, "/")

    msg = await transport.receive_message()
    assert msg["_client"] is ws
