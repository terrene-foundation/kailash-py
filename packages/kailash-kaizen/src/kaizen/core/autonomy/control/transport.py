"""
Transport Abstract Base Class

Defines the abstract interface for bidirectional communication transports
used in the control protocol.

Design Principles:
- Abstract base class using abc.ABC and @abstractmethod
- All network operations are async (anyio compatible)
- AsyncIterator for message streaming
- Clear lifecycle: connect() -> write()/read() -> close()
- is_ready() for connection state checking

Transport Implementations:
- CLITransport: Terminal-based (stdin/stdout)
- HTTPTransport: Web-based (Server-Sent Events)
- StdioTransport: Subprocess communication
- MockTransport: In-memory testing (tests/utils/mock_transport.py)

Example:
    class MyTransport(Transport):
        async def connect(self) -> None:
            # Establish connection
            pass

        async def write(self, data: str) -> None:
            # Send data to client
            pass

        def read_messages(self) -> AsyncIterator[str]:
            # Return async iterator for messages
            pass

        async def close(self) -> None:
            # Close connection
            pass

        def is_ready(self) -> bool:
            # Check if transport is ready
            return True

See Also:
    - ADR-011: Control Protocol Architecture
    - tests/unit/core/autonomy/control/test_transport.py
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Protocol, runtime_checkable


@runtime_checkable
class TransportProtocol(Protocol):
    """
    Protocol for transport implementations.

    Uses @runtime_checkable to enable isinstance() checks at runtime.
    This allows duck-typed implementations without inheriting from Transport.
    """

    async def connect(self) -> None:
        """Establish connection."""
        ...

    async def write(self, data: str) -> None:
        """Send data to client."""
        ...

    def read_messages(self) -> AsyncIterator[str]:
        """Receive messages from client."""
        ...

    async def close(self) -> None:
        """Close connection."""
        ...

    def is_ready(self) -> bool:
        """Check if transport is ready."""
        ...


class Transport(ABC):
    """
    Abstract base class for bidirectional communication transports.

    Defines the interface for all transport implementations used in the
    control protocol. Transports handle the low-level communication between
    agent and client, abstracting away the specific transport mechanism
    (CLI, HTTP, stdio, etc.).

    All network operations are async using anyio for runtime-agnostic
    async support (asyncio/trio).

    Lifecycle:
        1. Create transport instance
        2. Call connect() to establish connection
        3. Use write() to send messages
        4. Use read_messages() to receive messages
        5. Call close() to clean up resources

    Thread Safety:
        Implementations should be thread-safe for concurrent read/write
        operations. Use appropriate locking mechanisms as needed.

    Example:
        transport = CLITransport()
        await transport.connect()

        await transport.write('{"type": "question", "data": {...}}')

        async for message in transport.read_messages():
            print(f"Received: {message}")
            break

        await transport.close()
    """

    @abstractmethod
    async def connect(self) -> None:
        """
        Establish connection to client.

        Called once before any read/write operations. Implementations should:
        - Initialize connection resources
        - Set up communication channels
        - Update ready state

        Raises:
            RuntimeError: If already connected
            ConnectionError: If connection fails

        Example:
            await transport.connect()
        """
        pass

    @abstractmethod
    async def write(self, data: str) -> None:
        """
        Send data to client.

        Writes a message string to the transport. Messages are typically
        JSON-serialized control requests or responses.

        Args:
            data: Message string to send (typically JSON)

        Raises:
            RuntimeError: If not connected
            ConnectionError: If connection is closed or write fails

        Example:
            await transport.write('{"request_id": "req_123", "type": "question"}')
        """
        pass

    @abstractmethod
    def read_messages(self) -> AsyncIterator[str]:
        """
        Receive messages from client.

        Returns an async iterator that yields messages as they arrive.
        Messages are streamed incrementally, not batched.

        The iterator should:
        - Yield messages as they become available
        - Block when no messages are ready
        - Support cancellation via anyio.CancelScope
        - Not buffer excessively (stream incrementally)

        Returns:
            AsyncIterator[str]: Async iterator yielding message strings

        Raises:
            RuntimeError: If not connected

        Example:
            async for message in transport.read_messages():
                response = json.loads(message)
                print(f"Got response: {response}")
                if done:
                    break
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """
        Close connection and clean up resources.

        Should be idempotent - safe to call multiple times.
        Implementations should:
        - Close all open connections/streams
        - Release resources (file handles, sockets, etc.)
        - Update ready state to False
        - Not raise errors if already closed

        Example:
            await transport.close()
            await transport.close()  # Safe to call again
        """
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        """
        Check if transport is ready for communication.

        Synchronous method for quick status checks without async overhead.

        Returns:
            bool: True if connected and ready, False otherwise

        Example:
            if transport.is_ready():
                await transport.write(message)
            else:
                await transport.connect()
        """
        pass


__all__ = [
    "Transport",
    "TransportProtocol",
]
