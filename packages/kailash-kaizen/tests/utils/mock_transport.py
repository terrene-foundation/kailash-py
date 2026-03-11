"""
Mock Transport Implementation for Testing

Provides an in-memory mock transport for testing control protocol communication
without real network I/O.

Features:
- In-memory message queues
- Full lifecycle support (connect/write/read/close)
- Thread-safe concurrent operations
- Tracks written messages for assertions
- Queue messages for reading

Example:
    transport = MockTransport()
    await transport.connect()

    # Write messages
    await transport.write('{"test": "data"}')

    # Queue messages for reading
    transport.queue_message('{"response": "ok"}')

    # Read messages
    async for msg in transport.read_messages():
        print(msg)

    await transport.close()
"""

from collections import deque
from typing import AsyncIterator

import anyio
from kaizen.core.autonomy.control.transport import Transport


class MockTransport(Transport):
    """
    Mock transport for testing control protocol.

    Uses in-memory queues for bidirectional communication without network I/O.
    Tracks all written messages for test assertions.
    """

    def __init__(self):
        """Initialize mock transport with empty queues."""
        self._connected = False
        self.written_messages: list[str] = []  # Track all written messages
        self._read_queue: deque[str] = deque()  # Messages to be read
        self._send_stream = None
        self._receive_stream = None

    async def connect(self) -> None:
        """
        Establish mock connection.

        Creates in-memory streams for message passing.

        Raises:
            RuntimeError: If already connected
        """
        if self._connected:
            raise RuntimeError("Transport already connected")

        # Create memory object streams for async messaging
        self._send_stream, self._receive_stream = anyio.create_memory_object_stream(
            max_buffer_size=100
        )
        self._connected = True

    async def write(self, data: str) -> None:
        """
        Write message to transport.

        Args:
            data: Message string to write

        Raises:
            RuntimeError: If not connected
            ConnectionError: If connection is closed
        """
        if not self._connected:
            raise RuntimeError(
                "Cannot write to transport: not connected. " "Call connect() first."
            )

        if self._send_stream is None:
            raise ConnectionError("Cannot write to transport: connection closed")

        # Track message for assertions
        self.written_messages.append(data)

    def read_messages(self) -> AsyncIterator[str]:
        """
        Read messages from transport.

        Returns async iterator that yields messages from the queue.

        Returns:
            AsyncIterator[str]: Async iterator of messages

        Raises:
            RuntimeError: If not connected

        Example:
            async for message in transport.read_messages():
                print(f"Received: {message}")
        """
        if not self._connected:
            raise RuntimeError(
                "Cannot read from transport: not connected. " "Call connect() first."
            )

        return self._read_messages_impl()

    async def _read_messages_impl(self) -> AsyncIterator[str]:
        """
        Internal async generator for reading messages.

        Yields messages from both the async stream and the synchronous queue.
        This allows tests to queue messages before iteration starts.
        """
        # First drain any pre-queued messages
        while self._read_queue:
            yield self._read_queue.popleft()

        # Then read from async stream
        if self._receive_stream:
            async with self._receive_stream:
                async for message in self._receive_stream:
                    yield message

    async def close(self) -> None:
        """
        Close transport connection.

        Idempotent - safe to call multiple times.
        Cleans up async streams and resets state.
        """
        if not self._connected:
            return  # Already closed, idempotent

        # Close streams if they exist
        if self._send_stream:
            await self._send_stream.aclose()
            self._send_stream = None

        if self._receive_stream:
            await self._receive_stream.aclose()
            self._receive_stream = None

        self._connected = False

    def is_ready(self) -> bool:
        """
        Check if transport is ready for communication.

        Returns:
            bool: True if connected and ready, False otherwise
        """
        return self._connected

    # ============================================
    # Test Helper Methods
    # ============================================

    def queue_message(self, message: str) -> None:
        """
        Queue a message for reading.

        Helper method for tests to simulate incoming messages.

        Args:
            message: Message string to queue

        Example:
            transport.queue_message('{"response": "ok"}')
            async for msg in transport.read_messages():
                assert msg == '{"response": "ok"}'
        """
        if self._send_stream and self._connected:
            # If connected and streaming, send via stream
            # Use nowait to avoid blocking in test setup
            try:
                self._send_stream.send_nowait(message)
            except anyio.WouldBlock:
                # If stream is full, fall back to queue
                self._read_queue.append(message)
        else:
            # Not connected yet, queue for later
            self._read_queue.append(message)

    def clear_written_messages(self) -> None:
        """
        Clear the written messages list.

        Helper for tests that need to reset message history.
        """
        self.written_messages.clear()

    def get_written_messages(self) -> list[str]:
        """
        Get all messages written to transport.

        Returns:
            list[str]: Copy of written messages list
        """
        return self.written_messages.copy()

    def queue_response(self, message_type: str, data: dict) -> None:
        """
        Queue a response matching the last written request.

        Convenience method that automatically extracts request_id from the
        last written message and creates a properly formatted ControlResponse.

        Args:
            message_type: Expected message type (for validation)
            data: Response data dict (e.g., {"answer": "value"})

        Raises:
            ValueError: If no request has been written yet
            ValueError: If last request type doesn't match expected type

        Example:
            # After agent writes a question request:
            transport.queue_response("question", {"answer": "Alice"})
        """

        from kaizen.core.autonomy.control.types import ControlRequest, ControlResponse

        # Get last written request
        if not self.written_messages:
            raise ValueError("No request written yet - cannot queue response")

        last_request_json = self.written_messages[-1]
        try:
            request = ControlRequest.from_json(last_request_json)
        except Exception as e:
            raise ValueError(
                f"Failed to parse last written message as ControlRequest: {e}"
            )

        # Validate message type matches
        if request.type != message_type:
            raise ValueError(
                f"Request type mismatch: expected '{message_type}', "
                f"got '{request.type}'"
            )

        # Create matching response
        response = ControlResponse(request_id=request.request_id, data=data)

        # Queue response
        self.queue_message(response.to_json())

    def queue_error_response(self, message_type: str, error_message: str) -> None:
        """
        Queue an error response matching the last written request.

        Convenience method for simulating error responses in tests.

        Args:
            message_type: Expected message type (for validation)
            error_message: Error message to include in response

        Raises:
            ValueError: If no request has been written yet
            ValueError: If last request type doesn't match expected type

        Example:
            # After agent writes a request:
            transport.queue_error_response("question", "User cancelled")
        """

        from kaizen.core.autonomy.control.types import ControlRequest, ControlResponse

        # Get last written request
        if not self.written_messages:
            raise ValueError("No request written yet - cannot queue error response")

        last_request_json = self.written_messages[-1]
        try:
            request = ControlRequest.from_json(last_request_json)
        except Exception as e:
            raise ValueError(
                f"Failed to parse last written message as ControlRequest: {e}"
            )

        # Validate message type matches
        if request.type != message_type:
            raise ValueError(
                f"Request type mismatch: expected '{message_type}', "
                f"got '{request.type}'"
            )

        # Create error response
        response = ControlResponse(
            request_id=request.request_id, data={}, error=error_message
        )

        # Queue response
        self.queue_message(response.to_json())


__all__ = ["MockTransport"]
