# Custom Transport Development Guide

**Audience**: Developers creating custom transport implementations
**Time**: 15 minutes
**Prerequisites**: Understanding of Control Protocol basics

---

## Overview

Custom transports enable Control Protocol communication over any channel. This guide shows how to implement a custom transport from scratch.

**Use Cases**:
- WebSocket transport for real-time bidirectional communication
- gRPC transport for high-performance scenarios
- Message queue transport (RabbitMQ, Kafka) for distributed systems
- Custom protocol for specialized hardware/embedded systems

---

## Transport Interface

All transports implement the `Transport` ABC:

```python
from kaizen.core.autonomy.control.transport import Transport

class Transport(ABC):
    @abstractmethod
    async def connect(self) -> None:
        """Establish connection (if needed)."""

    @abstractmethod
    async def write(self, message: str) -> None:
        """Write message to transport."""

    @abstractmethod
    async def read_messages(self) -> AsyncIterator[str]:
        """Read messages from transport (async generator)."""

    @abstractmethod
    async def close(self) -> None:
        """Close connection and cleanup."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Check if transport is ready."""
```

---

## Example: WebSocket Transport

Here's a complete WebSocket transport implementation:

```python
"""
WebSocket Transport for Control Protocol

Enables bidirectional communication over WebSocket for web applications
with persistent connections and real-time updates.
"""

import anyio
from typing import AsyncIterator
import websockets

from kaizen.core.autonomy.control.transport import Transport


class WebSocketTransport(Transport):
    """
    WebSocket-based transport for real-time communication.

    Example:
        >>> transport = WebSocketTransport(ws_url="ws://localhost:8000/control")
        >>> await transport.connect()
        >>> await transport.write('{"type": "question", "data": {...}}')
        >>> async for message in transport.read_messages():
        ...     print(f"Received: {message}")
    """

    def __init__(self, ws_url: str):
        """
        Initialize WebSocket transport.

        Args:
            ws_url: WebSocket URL (e.g., "ws://localhost:8000/control")
        """
        self.ws_url = ws_url
        self._websocket = None
        self._connected = False

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        self._websocket = await websockets.connect(self.ws_url)
        self._connected = True

    async def write(self, message: str) -> None:
        """
        Write message to WebSocket.

        Args:
            message: JSON string to send

        Raises:
            RuntimeError: If not connected
        """
        if not self._connected or self._websocket is None:
            raise RuntimeError("WebSocket not connected. Call connect() first.")

        await self._websocket.send(message)

    async def read_messages(self) -> AsyncIterator[str]:
        """
        Read messages from WebSocket.

        Yields:
            JSON message strings

        Raises:
            RuntimeError: If not connected
        """
        if not self._connected or self._websocket is None:
            raise RuntimeError("WebSocket not connected. Call connect() first.")

        try:
            async for message in self._websocket:
                yield message
        except websockets.exceptions.ConnectionClosed:
            self._connected = False
            raise RuntimeError("WebSocket connection closed")

    async def close(self) -> None:
        """Close WebSocket connection."""
        if self._websocket is not None:
            await self._websocket.close()
            self._connected = False

    def is_ready(self) -> bool:
        """Check if WebSocket is ready."""
        return self._connected and self._websocket is not None
```

---

## Implementation Checklist

### 1. Connection Management ✅

**Initialize in `__init__`:**
```python
def __init__(self, connection_params):
    self._connection = None
    self._ready = False
```

**Establish in `connect()`:**
```python
async def connect(self) -> None:
    self._connection = await establish_connection(...)
    self._ready = True
```

**Check with `is_ready()`:**
```python
def is_ready(self) -> bool:
    return self._ready and self._connection is not None
```

### 2. Message Writing ✅

**Validate before writing:**
```python
async def write(self, message: str) -> None:
    if not self.is_ready():
        raise RuntimeError("Transport not ready")

    # Send message over your protocol
    await self._connection.send(message)
```

### 3. Message Reading ✅

**Use async generator pattern:**
```python
async def read_messages(self) -> AsyncIterator[str]:
    if not self.is_ready():
        raise RuntimeError("Transport not ready")

    while self._ready:
        message = await self._connection.receive()
        yield message
```

### 4. Cleanup ✅

**Close all resources:**
```python
async def close(self) -> None:
    if self._connection:
        await self._connection.close()
    self._ready = False
```

---

## Testing Your Transport

### Unit Tests

```python
import pytest
from your_module import YourTransport


@pytest.mark.asyncio
async def test_connect():
    """Test connection establishment."""
    transport = YourTransport(...)
    await transport.connect()
    assert transport.is_ready()
    await transport.close()


@pytest.mark.asyncio
async def test_write_message():
    """Test message writing."""
    transport = YourTransport(...)
    await transport.connect()

    # Should not raise
    await transport.write('{"type": "test"}')

    await transport.close()


@pytest.mark.asyncio
async def test_read_messages():
    """Test message reading."""
    transport = YourTransport(...)
    await transport.connect()

    # Simulate receiving messages
    messages = []
    async for msg in transport.read_messages():
        messages.append(msg)
        if len(messages) >= 3:
            break

    assert len(messages) == 3
    await transport.close()
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_bidirectional_communication():
    """Test full request/response cycle."""
    from kaizen.core.autonomy.control.protocol import ControlProtocol

    transport = YourTransport(...)
    await transport.connect()

    protocol = ControlProtocol(transport)

    async with anyio.create_task_group() as tg:
        await protocol.start(tg)

        # Send request and wait for response
        from kaizen.core.autonomy.control.types import ControlRequest
        request = ControlRequest.create("question", {"question": "Test?"})

        # Simulate response in background
        async def send_response():
            await anyio.sleep(0.1)
            response_json = f'{{"request_id": "{request.request_id}", "data": {{"answer": "Yes"}}}}'
            await transport.write(response_json)

        tg.start_soon(send_response)

        # Wait for response
        response = await protocol.send_request(request, timeout=1.0)
        assert response.data["answer"] == "Yes"

        await protocol.stop()

    await transport.close()
```

---

## Common Patterns

### Pattern 1: Connection Pooling

For high-performance scenarios:

```python
class PooledTransport(Transport):
    def __init__(self, pool_size=10):
        self._pool = []
        self._pool_size = pool_size

    async def connect(self):
        for _ in range(self._pool_size):
            conn = await create_connection()
            self._pool.append(conn)
```

### Pattern 2: Retry Logic

For unreliable networks:

```python
async def write(self, message: str) -> None:
    max_retries = 3
    for attempt in range(max_retries):
        try:
            await self._connection.send(message)
            return
        except NetworkError:
            if attempt == max_retries - 1:
                raise
            await anyio.sleep(2 ** attempt)  # Exponential backoff
```

### Pattern 3: Message Buffering

For batch operations:

```python
class BufferedTransport(Transport):
    def __init__(self, buffer_size=100):
        self._buffer = []
        self._buffer_size = buffer_size

    async def write(self, message: str):
        self._buffer.append(message)
        if len(self._buffer) >= self._buffer_size:
            await self._flush()

    async def _flush(self):
        if self._buffer:
            await self._connection.send_batch(self._buffer)
            self._buffer.clear()
```

---

## Best Practices

### 1. Error Handling ✅

Always handle transport-specific errors:

```python
async def read_messages(self) -> AsyncIterator[str]:
    try:
        async for message in self._connection.receive():
            yield message
    except ConnectionError as e:
        self._ready = False
        raise RuntimeError(f"Connection lost: {e}")
```

### 2. Resource Cleanup ✅

Use context managers when possible:

```python
class YourTransport(Transport):
    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

# Usage
async with YourTransport(...) as transport:
    await transport.write(...)
```

### 3. Logging ✅

Add logging for debugging:

```python
import logging

logger = logging.getLogger(__name__)

async def write(self, message: str):
    logger.debug(f"Sending message: {message[:100]}...")
    await self._connection.send(message)
    logger.debug("Message sent successfully")
```

---

## Example: Redis Pub/Sub Transport

Complete example for distributed systems:

```python
import anyio
import redis.asyncio as redis
from typing import AsyncIterator

from kaizen.core.autonomy.control.transport import Transport


class RedisPubSubTransport(Transport):
    """Redis Pub/Sub transport for distributed agent communication."""

    def __init__(self, redis_url: str, channel: str):
        self.redis_url = redis_url
        self.channel = channel
        self._redis = None
        self._pubsub = None
        self._ready = False

    async def connect(self) -> None:
        self._redis = await redis.from_url(self.redis_url)
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(self.channel)
        self._ready = True

    async def write(self, message: str) -> None:
        if not self._ready:
            raise RuntimeError("Not connected")
        await self._redis.publish(self.channel, message)

    async def read_messages(self) -> AsyncIterator[str]:
        if not self._ready:
            raise RuntimeError("Not connected")

        async for message in self._pubsub.listen():
            if message["type"] == "message":
                yield message["data"].decode("utf-8")

    async def close(self) -> None:
        if self._pubsub:
            await self._pubsub.unsubscribe(self.channel)
            await self._pubsub.close()
        if self._redis:
            await self._redis.close()
        self._ready = False

    def is_ready(self) -> bool:
        return self._ready
```

---

## Next Steps

1. **Implement your transport** following the interface
2. **Write comprehensive tests** (unit + integration)
3. **Test with Control Protocol** using real agent scenarios
4. **Document usage** for your team
5. **Consider contributing** to Kaizen if generally useful

---

## See Also

- **API Reference**: [Control Protocol API](../reference/control-protocol-api.md)
- **Built-in Transports**: `src/kaizen/core/autonomy/control/transports/`
- **Tutorial**: [Control Protocol Quickstart](control-protocol-tutorial.md)

---

**Last Updated**: 2025-10-20
