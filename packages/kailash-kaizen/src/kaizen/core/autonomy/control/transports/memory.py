"""
In-Memory Transport for Performance Testing

Provides real async I/O using anyio memory streams for accurate performance
benchmarking of the Control Protocol without network or subprocess overhead.

This is NOT a mock - it uses real anyio async streams with zero I/O overhead,
making it ideal for measuring pure protocol performance.

Design:
- Uses anyio.create_memory_object_stream() for real async channels
- Bidirectional: separate send/receive streams
- Zero overhead: In-memory only, no syscalls
- Real backpressure: Proper async stream semantics
- Thread-safe: Uses anyio primitives

Use Cases:
- Performance benchmarking
- Protocol overhead measurement
- Latency testing without I/O noise

Example:
    transport = InMemoryTransport()
    await transport.connect()

    # Write message
    await transport.write('{"type": "question"}')

    # Read messages
    async for message in transport.read_messages():
        print(f"Received: {message}")
        break

    await transport.close()
"""

from typing import AsyncIterator

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from kaizen.core.autonomy.control.transport import Transport


class InMemoryTransport(Transport):
    """
    In-memory transport using anyio memory streams.

    Provides real async I/O for performance testing without network overhead.
    Uses anyio.create_memory_object_stream() for bidirectional communication.

    Key Characteristics:
    - Real async: Uses anyio streams, not mocks
    - Zero I/O: In-memory only, no syscalls
    - Accurate: Measures pure protocol overhead
    - Backpressure: Proper async stream semantics

    Architecture:
    - write_send/write_receive: For outgoing messages (write -> read_messages)
    - read_send/read_receive: For incoming messages (from responder)

    Lifecycle:
        transport = InMemoryTransport()
        await transport.connect()  # Creates streams
        await transport.write(msg)  # Writes to write_send
        async for msg in transport.read_messages():  # Reads from read_receive
            ...
        await transport.close()  # Closes all streams
    """

    def __init__(self, buffer_size: int = 100):
        """
        Initialize in-memory transport.

        Args:
            buffer_size: Size of memory stream buffers (default: 100)
        """
        self.buffer_size = buffer_size
        self._connected = False

        # Streams for outgoing messages (write -> responder)
        self.write_send: MemoryObjectSendStream | None = None
        self.write_receive: MemoryObjectReceiveStream | None = None

        # Streams for incoming messages (responder -> read_messages)
        self.read_send: MemoryObjectSendStream | None = None
        self.read_receive: MemoryObjectReceiveStream | None = None

    async def connect(self) -> None:
        """
        Create memory streams for bidirectional communication.

        Creates two pairs of streams:
        1. write_send/write_receive: For outgoing messages
        2. read_send/read_receive: For incoming messages
        """
        if self._connected:
            return  # Idempotent

        # Create outgoing stream (write -> read by responder)
        self.write_send, self.write_receive = anyio.create_memory_object_stream(
            max_buffer_size=self.buffer_size
        )

        # Create incoming stream (responder writes -> read_messages)
        self.read_send, self.read_receive = anyio.create_memory_object_stream(
            max_buffer_size=self.buffer_size
        )

        self._connected = True

    async def write(self, message: str) -> None:
        """
        Write message to outgoing stream.

        Args:
            message: JSON string to write

        Raises:
            RuntimeError: If not connected
        """
        if not self._connected or self.write_send is None:
            raise RuntimeError("Transport not connected. Call connect() first.")

        await self.write_send.send(message)

    async def read_messages(self) -> AsyncIterator[str]:
        """
        Read messages from incoming stream.

        Yields:
            JSON message strings from responder

        Raises:
            RuntimeError: If not connected
        """
        if not self._connected or self.read_receive is None:
            raise RuntimeError("Transport not connected. Call connect() first.")

        # Don't use async with - that would close the stream
        # The stream will be closed in close() method
        async for message in self.read_receive:
            yield message

    async def close(self) -> None:
        """
        Close all memory streams.

        Idempotent - safe to call multiple times.
        Closes all four streams (send/receive for write/read).
        """
        if not self._connected:
            return  # Already closed

        # Close all streams
        if self.write_send:
            await self.write_send.aclose()
        if self.write_receive:
            await self.write_receive.aclose()
        if self.read_send:
            await self.read_send.aclose()
        if self.read_receive:
            await self.read_receive.aclose()

        self._connected = False

    def is_ready(self) -> bool:
        """Check if transport is connected and ready."""
        return self._connected

    def get_write_receiver(self) -> MemoryObjectReceiveStream:
        """
        Get the receive end of the write stream.

        This is used by the responder to read messages written by the protocol.

        Returns:
            Receive stream for reading written messages

        Raises:
            RuntimeError: If not connected
        """
        if not self._connected or self.write_receive is None:
            raise RuntimeError("Transport not connected")
        return self.write_receive

    def get_read_sender(self) -> MemoryObjectSendStream:
        """
        Get the send end of the read stream.

        This is used by the responder to send messages that will be read
        by the protocol's read_messages().

        Returns:
            Send stream for writing responses

        Raises:
            RuntimeError: If not connected
        """
        if not self._connected or self.read_send is None:
            raise RuntimeError("Transport not connected")
        return self.read_send
