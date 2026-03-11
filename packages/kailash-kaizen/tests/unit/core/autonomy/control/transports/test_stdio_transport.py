"""
Tier 1 Unit Tests for StdioTransport

Tests StdioTransport with mocked stdin/stdout for isolated unit testing.

Test Strategy:
- Unit-level tests with mocked I/O (no real subprocess)
- Test class structure and interface compliance
- Test state management and lifecycle
- Test error conditions and edge cases
- Fast execution (<1 second per test)

Coverage Requirements:
1. Test StdioTransport instantiation
2. Test inherits from Transport ABC
3. Test always ready (even before connect)
4. Test connect() is no-op/idempotent
5. Test write() sends to stdout
6. Test write() flushes immediately
7. Test read_messages() reads from stdin
8. Test read_messages() skips empty lines
9. Test close() is safe (doesn't close stdin/stdout)
10. Test close() is idempotent

Design from TODO-159 Week 9:
- StdioTransport is nearly identical to CLITransport
- Key difference: Semantic (subprocess-to-subprocess vs interactive terminal)
- Always ready (stdin/stdout always available)
- connect() is true no-op
- close() doesn't nullify streams (safe for stdin/stdout)

Target: 10/10 unit tests
Timeout: <1 second per test
"""

import sys
from unittest.mock import AsyncMock, patch

import anyio
import pytest

# Configure pytest for async tests
pytestmark = pytest.mark.anyio

# Import will work after implementation
try:
    from kaizen.core.autonomy.control.transports.stdio import StdioTransport
except ImportError:
    # Placeholder for TDD - tests will fail until implementation exists
    StdioTransport = None


# ============================================
# Test 1: Instantiation
# ============================================


class TestStdioTransportInstantiation:
    """Test StdioTransport can be instantiated."""

    def test_stdio_transport_can_be_instantiated(self):
        """Test that StdioTransport can be created with no parameters."""
        if StdioTransport is None:
            pytest.skip("StdioTransport not yet implemented")

        transport = StdioTransport()
        assert transport is not None

        # Verify it has all required Transport ABC methods
        assert hasattr(transport, "connect")
        assert hasattr(transport, "write")
        assert hasattr(transport, "read_messages")
        assert hasattr(transport, "close")
        assert hasattr(transport, "is_ready")

    def test_stdio_transport_no_parameters_required(self):
        """Test that StdioTransport takes no initialization parameters."""
        if StdioTransport is None:
            pytest.skip("StdioTransport not yet implemented")

        # Should work with no arguments (always uses sys.stdin/stdout)
        transport = StdioTransport()
        assert transport is not None


# ============================================
# Test 2: Inheritance
# ============================================


class TestStdioTransportInheritance:
    """Test StdioTransport inherits from Transport ABC."""

    def test_stdio_transport_inherits_from_transport(self):
        """Test that StdioTransport inherits from Transport ABC."""
        if StdioTransport is None:
            pytest.skip("StdioTransport not yet implemented")

        from kaizen.core.autonomy.control.transport import Transport

        transport = StdioTransport()
        assert isinstance(transport, Transport)

    def test_stdio_transport_implements_all_abstract_methods(self):
        """Test that StdioTransport implements all Transport ABC methods."""
        if StdioTransport is None:
            pytest.skip("StdioTransport not yet implemented")

        import inspect

        from kaizen.core.autonomy.control.transport import Transport

        # Get all abstract methods from Transport
        abstract_methods = {
            name
            for name, method in inspect.getmembers(Transport, inspect.isfunction)
            if getattr(method, "__isabstractmethod__", False)
        }

        # StdioTransport should implement all of them
        transport = StdioTransport()
        implemented_methods = {
            name
            for name in dir(transport)
            if not name.startswith("_") and callable(getattr(transport, name))
        }

        # All abstract methods should be implemented
        assert abstract_methods.issubset(implemented_methods)


# ============================================
# Test 3: Always Ready (Even Before Connect)
# ============================================


class TestStdioTransportAlwaysReady:
    """Test StdioTransport is always ready (stdin/stdout always available)."""

    def test_stdio_transport_ready_before_connect(self):
        """
        Test that StdioTransport is ready even before connect().

        Unlike CLITransport which needs connect() first, StdioTransport
        is always ready because stdin/stdout are always available.
        """
        if StdioTransport is None:
            pytest.skip("StdioTransport not yet implemented")

        transport = StdioTransport()

        # Key difference from CLITransport: should be ready immediately
        assert transport.is_ready()

    def test_stdio_transport_ready_after_connect(self):
        """Test that StdioTransport remains ready after connect()."""
        if StdioTransport is None:
            pytest.skip("StdioTransport not yet implemented")

        async def test_ready_after_connect():
            transport = StdioTransport()
            await transport.connect()

            # Should still be ready
            assert transport.is_ready()

            await transport.close()

        anyio.run(test_ready_after_connect)


# ============================================
# Test 4: Connect is No-Op/Idempotent
# ============================================


class TestStdioTransportConnect:
    """Test StdioTransport connect() is a no-op."""

    async def test_connect_is_noop(self):
        """
        Test that connect() is a no-op (doesn't do anything).

        StdioTransport doesn't need connection setup because
        stdin/stdout are always available.
        """
        if StdioTransport is None:
            pytest.skip("StdioTransport not yet implemented")

        transport = StdioTransport()

        # Should already be ready
        assert transport.is_ready()

        # Connect should not raise and not change state
        await transport.connect()

        # Still ready
        assert transport.is_ready()

    async def test_connect_is_idempotent(self):
        """Test that connect() can be called multiple times safely."""
        if StdioTransport is None:
            pytest.skip("StdioTransport not yet implemented")

        transport = StdioTransport()

        # Call connect multiple times
        await transport.connect()
        await transport.connect()
        await transport.connect()

        # Should not raise, should remain ready
        assert transport.is_ready()

    async def test_connect_completes_immediately(self):
        """Test that connect() completes immediately (no blocking)."""
        if StdioTransport is None:
            pytest.skip("StdioTransport not yet implemented")

        import time

        transport = StdioTransport()

        start = time.time()
        await transport.connect()
        elapsed = time.time() - start

        # Should complete in <10ms (essentially instant)
        assert elapsed < 0.01


# ============================================
# Test 5: Write Sends to Stdout
# ============================================


class TestStdioTransportWrite:
    """Test StdioTransport write() sends to stdout."""

    async def test_write_sends_to_stdout(self):
        """Test that write() sends data to stdout."""
        if StdioTransport is None:
            pytest.skip("StdioTransport not yet implemented")

        # Mock stdout to capture writes
        mock_stdout = AsyncMock()
        mock_stdout.write = AsyncMock()
        mock_stdout.flush = AsyncMock()

        with patch("anyio.wrap_file", return_value=mock_stdout):
            transport = StdioTransport()
            await transport.connect()

            test_data = '{"test": "data"}'
            await transport.write(test_data)

            # Verify write was called with data + newline
            mock_stdout.write.assert_called_once()
            call_args = mock_stdout.write.call_args[0][0]
            assert test_data in call_args
            assert call_args.endswith("\n")

    async def test_write_adds_newline(self):
        """Test that write() adds newline to data (line-based protocol)."""
        if StdioTransport is None:
            pytest.skip("StdioTransport not yet implemented")

        mock_stdout = AsyncMock()
        mock_stdout.write = AsyncMock()
        mock_stdout.flush = AsyncMock()

        with patch("anyio.wrap_file", return_value=mock_stdout):
            transport = StdioTransport()
            await transport.connect()

            test_data = '{"message": "hello"}'
            await transport.write(test_data)

            # Should add newline
            call_args = mock_stdout.write.call_args[0][0]
            assert call_args == test_data + "\n"


# ============================================
# Test 6: Write Flushes Immediately
# ============================================


class TestStdioTransportWriteFlush:
    """Test StdioTransport write() flushes immediately."""

    async def test_write_flushes_immediately(self):
        """
        Test that write() flushes stdout immediately.

        Critical for subprocess communication - data must be
        delivered immediately, not buffered.
        """
        if StdioTransport is None:
            pytest.skip("StdioTransport not yet implemented")

        mock_stdout = AsyncMock()
        mock_stdout.write = AsyncMock()
        mock_stdout.flush = AsyncMock()

        with patch("anyio.wrap_file", return_value=mock_stdout):
            transport = StdioTransport()
            await transport.connect()

            await transport.write('{"test": "flush"}')

            # Verify flush was called
            mock_stdout.flush.assert_called_once()

    async def test_write_flush_called_after_write(self):
        """Test that flush() is called AFTER write()."""
        if StdioTransport is None:
            pytest.skip("StdioTransport not yet implemented")

        call_order = []

        mock_stdout = AsyncMock()
        mock_stdout.write = AsyncMock(side_effect=lambda _: call_order.append("write"))
        mock_stdout.flush = AsyncMock(side_effect=lambda: call_order.append("flush"))

        with patch("anyio.wrap_file", return_value=mock_stdout):
            transport = StdioTransport()
            await transport.connect()

            await transport.write('{"order": "test"}')

            # Verify order: write then flush
            assert call_order == ["write", "flush"]


# ============================================
# Test 7: Read Messages from Stdin
# ============================================


class TestStdioTransportReadMessages:
    """Test StdioTransport read_messages() reads from stdin."""

    async def test_read_messages_yields_from_stdin(self):
        """Test that read_messages() yields messages from stdin."""
        if StdioTransport is None:
            pytest.skip("StdioTransport not yet implemented")

        # Mock stdin with test messages
        async def mock_stdin_iterator():
            """Simulate stdin yielding lines."""
            yield '{"message": "line1"}\n'
            yield '{"message": "line2"}\n'

        mock_stdin = AsyncMock()
        mock_stdin.__aiter__ = lambda self: mock_stdin_iterator()

        with patch("anyio.wrap_file", return_value=mock_stdin):
            transport = StdioTransport()
            await transport.connect()

            messages = []
            async for message in transport.read_messages():
                messages.append(message)
                if len(messages) >= 2:
                    break

            # Should receive both messages
            assert len(messages) == 2
            assert '"line1"' in messages[0]
            assert '"line2"' in messages[1]

    async def test_read_messages_strips_whitespace(self):
        """Test that read_messages() strips leading/trailing whitespace."""
        if StdioTransport is None:
            pytest.skip("StdioTransport not yet implemented")

        async def mock_stdin_iterator():
            """Simulate stdin with whitespace."""
            yield '  {"message": "test"}  \n'
            yield '\t{"message": "test2"}\t\n'

        mock_stdin = AsyncMock()
        mock_stdin.__aiter__ = lambda self: mock_stdin_iterator()

        with patch("anyio.wrap_file", return_value=mock_stdin):
            transport = StdioTransport()
            await transport.connect()

            messages = []
            async for message in transport.read_messages():
                messages.append(message)
                if len(messages) >= 2:
                    break

            # Should strip whitespace
            assert messages[0] == '{"message": "test"}'
            assert messages[1] == '{"message": "test2"}'


# ============================================
# Test 8: Read Messages Skips Empty Lines
# ============================================


class TestStdioTransportReadMessagesSkipEmpty:
    """Test StdioTransport read_messages() skips empty lines."""

    async def test_read_messages_skips_empty_lines(self):
        """
        Test that read_messages() skips empty lines.

        Empty lines should not be yielded as messages.
        """
        if StdioTransport is None:
            pytest.skip("StdioTransport not yet implemented")

        async def mock_stdin_iterator():
            """Simulate stdin with empty lines."""
            yield "\n"
            yield '{"message": "valid1"}\n'
            yield "   \n"  # Whitespace-only
            yield "\t\n"  # Tab-only
            yield '{"message": "valid2"}\n'
            yield "\n"

        mock_stdin = AsyncMock()
        mock_stdin.__aiter__ = lambda self: mock_stdin_iterator()

        with patch("anyio.wrap_file", return_value=mock_stdin):
            transport = StdioTransport()
            await transport.connect()

            messages = []
            async for message in transport.read_messages():
                messages.append(message)
                if len(messages) >= 2:
                    break

            # Should only receive valid messages (skip empty lines)
            assert len(messages) == 2
            assert '"valid1"' in messages[0]
            assert '"valid2"' in messages[1]

    async def test_read_messages_handles_consecutive_empty_lines(self):
        """Test handling of multiple consecutive empty lines."""
        if StdioTransport is None:
            pytest.skip("StdioTransport not yet implemented")

        async def mock_stdin_iterator():
            """Simulate stdin with many empty lines."""
            yield "\n"
            yield "\n"
            yield "\n"
            yield '{"message": "after_empty"}\n'

        mock_stdin = AsyncMock()
        mock_stdin.__aiter__ = lambda self: mock_stdin_iterator()

        with patch("anyio.wrap_file", return_value=mock_stdin):
            transport = StdioTransport()
            await transport.connect()

            messages = []
            async for message in transport.read_messages():
                messages.append(message)
                break

            # Should skip all empty lines and get first valid message
            assert len(messages) == 1
            assert '"after_empty"' in messages[0]


# ============================================
# Test 9: Close is Safe (Doesn't Close stdin/stdout)
# ============================================


class TestStdioTransportCloseSafe:
    """Test StdioTransport close() is safe (doesn't close stdin/stdout)."""

    async def test_close_does_not_close_stdin_stdout(self):
        """
        Test that close() doesn't close sys.stdin/sys.stdout.

        Critical: StdioTransport should NOT close the actual system
        stdin/stdout streams, only release references.
        """
        if StdioTransport is None:
            pytest.skip("StdioTransport not yet implemented")

        # Verify stdin/stdout are not closed
        original_stdin_closed = sys.stdin.closed
        original_stdout_closed = sys.stdout.closed

        transport = StdioTransport()
        await transport.connect()
        await transport.close()

        # sys.stdin and sys.stdout should still be open
        assert sys.stdin.closed == original_stdin_closed
        assert sys.stdout.closed == original_stdout_closed
        assert not sys.stdin.closed
        assert not sys.stdout.closed

    async def test_close_releases_references(self):
        """Test that close() releases internal stream references."""
        if StdioTransport is None:
            pytest.skip("StdioTransport not yet implemented")

        transport = StdioTransport()
        await transport.connect()

        # Transport should have references to wrapped streams
        # (implementation detail - may vary)

        await transport.close()

        # Should not be ready after close
        assert not transport.is_ready()


# ============================================
# Test 10: Close is Idempotent
# ============================================


class TestStdioTransportCloseIdempotent:
    """Test StdioTransport close() is idempotent."""

    async def test_close_is_idempotent(self):
        """Test that close() can be called multiple times safely."""
        if StdioTransport is None:
            pytest.skip("StdioTransport not yet implemented")

        transport = StdioTransport()
        await transport.connect()

        # Call close multiple times
        await transport.close()
        await transport.close()
        await transport.close()

        # Should not raise, should remain not ready
        assert not transport.is_ready()

    async def test_close_before_connect_is_safe(self):
        """Test that close() before connect() is safe."""
        if StdioTransport is None:
            pytest.skip("StdioTransport not yet implemented")

        transport = StdioTransport()

        # Close without connect - should not raise
        await transport.close()

        assert not transport.is_ready()

    async def test_close_then_connect_works(self):
        """Test that transport can be reconnected after close."""
        if StdioTransport is None:
            pytest.skip("StdioTransport not yet implemented")

        transport = StdioTransport()
        await transport.connect()
        assert transport.is_ready()

        await transport.close()
        assert not transport.is_ready()

        # Should be able to connect again
        await transport.connect()
        assert transport.is_ready()

        await transport.close()


# ============================================
# Test Summary
# ============================================


class TestStdioTransportSummary:
    """Summary test covering all key features."""

    async def test_complete_unit_test_coverage(self):
        """
        Summary test: verify all Transport ABC methods work.

        Tests:
        1. Instantiation (no parameters)
        2. Inheritance (Transport ABC)
        3. Always ready (before connect)
        4. Connect is no-op
        5. Write sends to stdout
        6. Write flushes immediately
        7. Read messages from stdin
        8. Skips empty lines
        9. Close is safe
        10. Close is idempotent
        """
        if StdioTransport is None:
            pytest.skip("StdioTransport not yet implemented")

        # Test instantiation and inheritance
        from kaizen.core.autonomy.control.transport import Transport

        transport = StdioTransport()
        assert isinstance(transport, Transport)

        # Test always ready
        assert transport.is_ready()

        # Test connect is no-op
        await transport.connect()
        assert transport.is_ready()

        # Mock I/O for testing write/read
        mock_stdout = AsyncMock()
        mock_stdout.write = AsyncMock()
        mock_stdout.flush = AsyncMock()

        async def mock_stdin_iterator():
            yield '{"test": "message"}\n'
            yield "\n"  # Empty line
            yield '{"test": "message2"}\n'

        mock_stdin = AsyncMock()
        mock_stdin.__aiter__ = lambda self: mock_stdin_iterator()

        with patch("anyio.wrap_file", side_effect=[mock_stdin, mock_stdout]):
            transport2 = StdioTransport()
            await transport2.connect()

            # Test write
            await transport2.write('{"test": "data"}')
            mock_stdout.write.assert_called_once()
            mock_stdout.flush.assert_called_once()

            # Test read (skip empty lines)
            messages = []
            async for msg in transport2.read_messages():
                messages.append(msg)
                if len(messages) >= 2:
                    break

            assert len(messages) == 2
            assert '"message"' in messages[0]
            assert '"message2"' in messages[1]

            # Test close is safe and idempotent
            await transport2.close()
            await transport2.close()
            assert not transport2.is_ready()
