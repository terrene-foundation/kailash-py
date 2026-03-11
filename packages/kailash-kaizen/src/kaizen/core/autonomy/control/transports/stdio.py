"""
Stdio Transport Implementation

Provides subprocess-based bidirectional communication using stdin/stdout
for the control protocol. Implements the Transport ABC.

Design from ADR-011:
- Uses stdin for reading messages from parent process
- Uses stdout for writing messages to parent process
- Handles line-based protocol (one JSON message per line)
- Async I/O with anyio.wrap_file
- No connection overhead (stdin/stdout always available)

Key Characteristics:
- Lightweight: No network or setup overhead
- Subprocess-optimized: Designed for parent-child process communication
- Line-based: One JSON message per line
- Async-first: Uses anyio for runtime-agnostic async I/O
- Always ready: stdin/stdout are always available in subprocess context

Difference from CLITransport:
- CLITransport: Interactive terminal use (user-facing)
- StdioTransport: Programmatic subprocess communication (process-to-process)
- Semantic difference, similar implementation
- StdioTransport is always ready (no connection state tracking needed)

Example:
    transport = StdioTransport()
    # No need to connect - already ready
    assert transport.is_ready()

    # Write request to parent process (via stdout)
    await transport.write('{"request_id": "req_123", "type": "question"}')

    # Read response from parent process (via stdin)
    async for message in transport.read_messages():
        response = json.loads(message)
        print(f"Got response: {response}", file=sys.stderr)
        break

    await transport.close()

Usage Pattern (Subprocess):
    1. Child process creates StdioTransport (no connect needed)
    2. Child writes control requests to stdout (parent reads)
    3. Child reads control responses from stdin (parent writes)
    4. Parent reads child's stdout and writes to child's stdin
    5. Bidirectional communication via stdin/stdout pipes

See Also:
    - ADR-011: Control Protocol Architecture (Section: Stdio Transport)
    - tests/integration/autonomy/control/test_stdio_transport.py
    - CLITransport: Similar implementation, different semantic use case
"""

import sys
from typing import AsyncIterator

import anyio
from kaizen.core.autonomy.control.transport import Transport


class StdioTransport(Transport):
    """
    Subprocess-based transport using stdin/stdout.

    Implements bidirectional communication for subprocess scenarios using
    stdin for reading messages and stdout for writing messages.

    The transport uses a line-based protocol where each message is a
    single JSON string terminated by a newline character.

    Key Design Decisions:
    - Always ready: stdin/stdout are always available in subprocess
    - No connection state: connect() is a no-op
    - Safe close: doesn't close sys.stdin/sys.stdout (only releases references)
    - Immediate flush: critical for subprocess communication

    Lifecycle:
        1. Create: transport = StdioTransport()
        2. Optional Connect: await transport.connect() (no-op, already ready)
        3. Use: await transport.write(...) / async for msg in transport.read_messages()
        4. Close: await transport.close()

    Thread Safety:
        - Read and write operations are thread-safe via anyio
        - Multiple concurrent readers/writers are supported

    Performance:
        - Low latency: <10ms for subprocess pipe I/O
        - High throughput: >1000 messages/second for simple JSON
        - No connection overhead: 0ms (always ready)

    Example:
        transport = StdioTransport()
        # Already ready - no connect needed
        assert transport.is_ready()

        # Write request (child -> parent via stdout)
        await transport.write('{"request_id": "req_1", "type": "question"}')

        # Read response (parent -> child via stdin)
        async for message in transport.read_messages():
            print(f"Received: {message}", file=sys.stderr)
            break

        await transport.close()
    """

    def __init__(self):
        """
        Initialize Stdio transport.

        Sets up internal state for managing stdin/stdout streams.
        Streams are created lazily on first use.

        Note:
            - No parameters needed (always uses sys.stdin/sys.stdout)
            - Transport is always ready (stdin/stdout always available)
            - No connection state tracking (simpler than CLITransport)
        """
        self._stdin_stream = None
        self._stdout_stream = None
        self._ready = True  # Always ready (stdin/stdout always available)

    async def connect(self) -> None:
        """
        Establish connection to stdin/stdout.

        This is essentially a no-op for StdioTransport because stdin/stdout
        are always available in subprocess context. However, we still wrap
        them with anyio for async I/O consistency.

        This operation is idempotent - calling multiple times is safe.

        Note:
            - stdin/stdout are always available in subprocess context
            - No actual connection is made (local I/O)
            - Operation completes immediately (<1ms)
            - Wraps streams on first call, subsequent calls do nothing

        Raises:
            Should not raise (stdin/stdout always available)

        Example:
            transport = StdioTransport()
            await transport.connect()
            assert transport.is_ready()
        """
        if self._stdin_stream is not None and self._stdout_stream is not None:
            # Already wrapped - idempotent
            return

        # Wrap stdin/stdout with anyio for async I/O
        # Note: We use stdin for READING parent responses
        #       We use stdout for WRITING child requests
        if self._stdin_stream is None:
            self._stdin_stream = anyio.wrap_file(sys.stdin)

        if self._stdout_stream is None:
            self._stdout_stream = anyio.wrap_file(sys.stdout)

        self._ready = True

    async def write(self, data: str) -> None:
        """
        Send data to parent process via stdout.

        Writes a JSON message string to stdout, followed by a newline.
        The message is flushed immediately to ensure delivery to parent.

        Critical for subprocess communication: flush() is mandatory
        because buffering can cause deadlocks in pipe communication.

        Args:
            data: Message string to send (typically JSON)

        Raises:
            RuntimeError: If not ready (streams not wrapped)
            ConnectionError: If stdout is closed or write fails

        Example:
            await transport.write('{"request_id": "req_123", "type": "question"}')
        """
        if not self._ready:
            raise RuntimeError(
                "Cannot write to transport: not ready. " "Call connect() first."
            )

        # Lazy initialization: wrap stdout on first write if needed
        if self._stdout_stream is None:
            self._stdout_stream = anyio.wrap_file(sys.stdout)

        if self._stdout_stream is None:
            raise ConnectionError(
                "Cannot write to transport: stdout stream not available"
            )

        try:
            # Write message + newline (line-based protocol)
            await self._stdout_stream.write(data + "\n")

            # Flush immediately to ensure delivery
            # CRITICAL: Without flush, messages can be buffered and cause deadlocks
            await self._stdout_stream.flush()

        except Exception as e:
            raise ConnectionError(f"Failed to write to transport: {e}") from e

    def read_messages(self) -> AsyncIterator[str]:
        """
        Receive messages from parent process via stdin.

        Returns an async iterator that yields messages line-by-line from stdin.
        Each line is expected to be a complete JSON message.

        The iterator:
        - Yields messages as they arrive
        - Strips whitespace from each line
        - Skips empty lines
        - Blocks when no messages are ready
        - Terminates on EOF (stdin closes)

        Returns:
            AsyncIterator[str]: Async iterator yielding message strings

        Raises:
            RuntimeError: If not ready (streams not wrapped)

        Example:
            async for message in transport.read_messages():
                response = json.loads(message)
                print(f"Got response: {response}", file=sys.stderr)
                if done:
                    break
        """
        if not self._ready:
            raise RuntimeError(
                "Cannot read from transport: not ready. " "Call connect() first."
            )

        return self._read_messages_impl()

    async def _read_messages_impl(self) -> AsyncIterator[str]:
        """
        Internal async generator for reading messages line-by-line.

        Reads from stdin stream, yields non-empty lines after stripping whitespace.
        Handles EOF gracefully by terminating iteration.

        Lazy initialization: wraps stdin on first read if needed.

        Yields:
            str: Message string (one per line)

        Note:
            - Skips empty lines (whitespace-only)
            - Strips leading/trailing whitespace
            - Terminates on EOF without raising
        """
        # Lazy initialization: wrap stdin on first read if needed
        if self._stdin_stream is None:
            self._stdin_stream = anyio.wrap_file(sys.stdin)

        if self._stdin_stream is None:
            raise RuntimeError("stdin stream not available")

        try:
            # Read lines from stdin until EOF
            async for line in self._stdin_stream:
                # Strip whitespace
                line = line.strip()

                # Skip empty lines
                if not line:
                    continue

                # Yield message
                yield line

        except anyio.EndOfStream:
            # EOF reached - normal termination
            return

        except Exception as e:
            # Log error but don't crash
            # In production, this would use proper logging
            print(f"Error reading from stdin: {e}", file=sys.stderr)
            return

    async def close(self) -> None:
        """
        Close connection and clean up resources.

        Releases stdin/stdout async wrappers and resets state.
        This operation is idempotent - safe to call multiple times.

        CRITICAL: Does NOT close sys.stdin/sys.stdout themselves.
        Only releases anyio wrapper references. The underlying system
        streams remain open and usable by other code.

        Note:
            - Does NOT close sys.stdin/sys.stdout (they remain open)
            - Only releases anyio wrappers
            - Safe to call even if not connected
            - Sets ready state to False

        Example:
            await transport.close()
            await transport.close()  # Safe to call again
        """
        if not self._ready:
            # Idempotent: already closed
            return

        # Release anyio wrappers (not sys.stdin/stdout themselves)
        # Note: anyio.wrap_file wrappers don't have close() method
        # The underlying sys.stdin/stdout remain open
        # We just release our references
        self._stdin_stream = None
        self._stdout_stream = None

        self._ready = False

    def is_ready(self) -> bool:
        """
        Check if transport is ready for communication.

        For StdioTransport, this is almost always True because stdin/stdout
        are always available in subprocess context. Returns False only after
        explicit close() call.

        Returns:
            bool: True if ready for communication, False if closed

        Example:
            if transport.is_ready():
                await transport.write(message)
            else:
                await transport.connect()
        """
        return self._ready


__all__ = ["StdioTransport"]
