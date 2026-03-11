"""
Tier 1 Unit Tests for Transport Abstract Base Class

Tests the Transport ABC and Protocol including:
- Abstract method enforcement (cannot instantiate ABC)
- Protocol runtime_checkable decorator
- MockTransport lifecycle (connect/write/read/close)
- AsyncIterator message streaming
- Edge cases: connection failures, read errors, close idempotence

Coverage Target: 100% for transport layer
Test Strategy: TDD - Tests written BEFORE implementation
Infrastructure: Mock transports with in-memory queues
"""

from typing import AsyncIterator

import anyio
import pytest

# Import will work after implementation
# Test abstract enforcement by trying to instantiate
try:
    from kaizen.core.autonomy.control.transport import Transport
except ImportError:
    # Placeholder for TDD - tests will fail until implementation exists
    Transport = None


# ============================================
# Test Fixtures
# ============================================


@pytest.fixture
def sample_messages() -> list[str]:
    """Sample messages for testing."""
    return [
        '{"request_id": "req_1", "type": "question", "data": {"q": "Test?"}}',
        '{"request_id": "req_2", "type": "approval", "data": {"action": "delete"}}',
        '{"request_id": "req_3", "type": "progress_update", "data": {"pct": 50}}',
    ]


# ============================================
# Abstract Base Class Tests
# ============================================


class TestTransportAbstractEnforcement:
    """Test that Transport is properly abstract and cannot be instantiated."""

    def test_transport_cannot_be_instantiated_directly(self):
        """Test that Transport ABC cannot be instantiated without implementing methods."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        # Attempting to instantiate Transport should raise TypeError
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            Transport()

    def test_transport_requires_all_abstract_methods(self):
        """Test that all abstract methods must be implemented."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        # Create incomplete implementation missing close()
        class IncompleteTransport(Transport):
            async def connect(self) -> None:
                pass

            async def write(self, data: str) -> None:
                pass

            def read_messages(self) -> AsyncIterator[str]:
                pass

            def is_ready(self) -> bool:
                return True

            # Missing: async def close(self) -> None

        # Should raise TypeError for missing abstract method
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteTransport()

    def test_transport_protocol_runtime_checkable(self):
        """Test that Transport uses @runtime_checkable Protocol."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        # Import typing.Protocol to check

        # Verify Transport has Protocol in MRO or uses runtime_checkable
        # This depends on implementation - either ABC or Protocol with runtime_checkable
        # We'll check that the type can be used with isinstance()
        assert hasattr(Transport, "__abstractmethods__") or hasattr(
            Transport, "_is_protocol"
        )


# ============================================
# MockTransport Implementation Tests
# ============================================


class TestMockTransport:
    """Test MockTransport implementation used for testing."""

    @pytest.mark.anyio
    async def test_mock_transport_creation(self):
        """Test creating a MockTransport instance."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        # Import will work after MockTransport is created
        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()
        assert transport is not None
        assert isinstance(transport, Transport)

    @pytest.mark.anyio
    async def test_mock_transport_connect(self):
        """Test MockTransport connect() method."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()
        assert not transport.is_ready()

        await transport.connect()
        assert transport.is_ready()

    @pytest.mark.anyio
    async def test_mock_transport_write(self):
        """Test MockTransport write() method."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()
        await transport.connect()

        # Write message
        test_message = '{"test": "data"}'
        await transport.write(test_message)

        # Verify message was written (MockTransport should store it)
        assert len(transport.written_messages) == 1
        assert transport.written_messages[0] == test_message

    @pytest.mark.anyio
    async def test_mock_transport_write_multiple_messages(self):
        """Test writing multiple messages."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()
        await transport.connect()

        messages = ["msg1", "msg2", "msg3"]
        for msg in messages:
            await transport.write(msg)

        assert len(transport.written_messages) == 3
        assert transport.written_messages == messages

    @pytest.mark.anyio
    async def test_mock_transport_read_messages_empty(self):
        """Test reading messages when queue is empty."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()
        await transport.connect()

        # Read with timeout (should not hang)
        messages_read = []
        try:
            with anyio.fail_after(0.1):
                async for msg in transport.read_messages():
                    messages_read.append(msg)
                    if len(messages_read) >= 1:  # Only try to read one
                        break
        except TimeoutError:
            pass  # Expected when queue is empty

        assert len(messages_read) == 0

    @pytest.mark.anyio
    async def test_mock_transport_read_messages_with_data(self, sample_messages):
        """Test reading messages from queue."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()
        await transport.connect()

        # Queue messages for reading
        for msg in sample_messages:
            transport.queue_message(msg)

        # Read messages
        messages_read = []
        with anyio.fail_after(1.0):
            async for msg in transport.read_messages():
                messages_read.append(msg)
                if len(messages_read) >= len(sample_messages):
                    break

        assert messages_read == sample_messages

    @pytest.mark.anyio
    async def test_mock_transport_close(self):
        """Test MockTransport close() method."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()
        await transport.connect()
        assert transport.is_ready()

        await transport.close()
        assert not transport.is_ready()

    @pytest.mark.anyio
    async def test_mock_transport_close_idempotent(self):
        """Test that calling close() multiple times is safe."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()
        await transport.connect()

        # Close multiple times should not raise error
        await transport.close()
        await transport.close()
        await transport.close()

        assert not transport.is_ready()

    @pytest.mark.anyio
    async def test_mock_transport_full_lifecycle(self, sample_messages):
        """Test complete lifecycle: connect -> write -> read -> close."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()

        # 1. Connect
        await transport.connect()
        assert transport.is_ready()

        # 2. Write messages
        for msg in sample_messages:
            await transport.write(msg)

        # 3. Queue responses to read
        responses = ["resp1", "resp2", "resp3"]
        for resp in responses:
            transport.queue_message(resp)

        # 4. Read messages
        messages_read = []
        with anyio.fail_after(1.0):
            async for msg in transport.read_messages():
                messages_read.append(msg)
                if len(messages_read) >= len(responses):
                    break

        assert messages_read == responses

        # 5. Close
        await transport.close()
        assert not transport.is_ready()


# ============================================
# Transport Interface Tests
# ============================================


class TestTransportInterface:
    """Test Transport interface contracts."""

    @pytest.mark.anyio
    async def test_connect_is_async(self):
        """Test that connect() is async."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()

        # connect() should be awaitable
        import inspect

        assert inspect.iscoroutinefunction(transport.connect)

        # Should work with await
        await transport.connect()

    @pytest.mark.anyio
    async def test_write_is_async(self):
        """Test that write() is async."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()
        await transport.connect()

        # write() should be awaitable
        import inspect

        assert inspect.iscoroutinefunction(transport.write)

        # Should work with await
        await transport.write("test")

    @pytest.mark.anyio
    async def test_read_messages_returns_async_iterator(self):
        """Test that read_messages() returns AsyncIterator."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()
        await transport.connect()

        # read_messages() should return async iterator
        result = transport.read_messages()

        # Check it's an async iterator
        assert hasattr(result, "__aiter__")
        assert hasattr(result, "__anext__")

    @pytest.mark.anyio
    async def test_close_is_async(self):
        """Test that close() is async."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()
        await transport.connect()

        # close() should be awaitable
        import inspect

        assert inspect.iscoroutinefunction(transport.close)

        # Should work with await
        await transport.close()

    def test_is_ready_is_synchronous(self):
        """Test that is_ready() is synchronous."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()

        # is_ready() should be synchronous
        import inspect

        assert not inspect.iscoroutinefunction(transport.is_ready)

        # Should return bool
        result = transport.is_ready()
        assert isinstance(result, bool)


# ============================================
# Edge Cases and Error Handling
# ============================================


class TestTransportEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.anyio
    async def test_write_before_connect_raises_error(self):
        """Test that writing before connect raises error."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()

        # Writing before connect should raise error
        with pytest.raises((RuntimeError, ValueError, ConnectionError)):
            await transport.write("test")

    @pytest.mark.anyio
    async def test_read_before_connect_raises_error(self):
        """Test that reading before connect raises error."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()

        # Reading before connect should raise error
        with pytest.raises((RuntimeError, ValueError, ConnectionError)):
            async for _ in transport.read_messages():
                break

    @pytest.mark.anyio
    async def test_write_after_close_raises_error(self):
        """Test that writing after close raises error."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()
        await transport.connect()
        await transport.close()

        # Writing after close should raise error
        with pytest.raises((RuntimeError, ValueError, ConnectionError)):
            await transport.write("test")

    @pytest.mark.anyio
    async def test_write_empty_string(self):
        """Test writing empty string."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()
        await transport.connect()

        # Empty string should be allowed
        await transport.write("")
        assert len(transport.written_messages) == 1
        assert transport.written_messages[0] == ""

    @pytest.mark.anyio
    async def test_write_large_message(self):
        """Test writing large message."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()
        await transport.connect()

        # Large message (1MB)
        large_message = "x" * (1024 * 1024)
        await transport.write(large_message)

        assert len(transport.written_messages) == 1
        assert len(transport.written_messages[0]) == 1024 * 1024

    @pytest.mark.anyio
    async def test_read_messages_with_special_characters(self):
        """Test reading messages with special characters."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()
        await transport.connect()

        # Messages with special characters
        special_messages = [
            '{"text": "Hello\\nWorld"}',
            '{"unicode": "世界 🌍"}',
            '{"quotes": "\\"test\\""}',
        ]

        for msg in special_messages:
            transport.queue_message(msg)

        messages_read = []
        with anyio.fail_after(1.0):
            async for msg in transport.read_messages():
                messages_read.append(msg)
                if len(messages_read) >= len(special_messages):
                    break

        assert messages_read == special_messages

    @pytest.mark.anyio
    async def test_concurrent_writes(self):
        """Test concurrent writes to transport."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()
        await transport.connect()

        # Write 10 messages concurrently
        async def write_message(msg: str):
            await transport.write(msg)

        async with anyio.create_task_group() as tg:
            for i in range(10):
                tg.start_soon(write_message, f"msg_{i}")

        # All messages should be written
        assert len(transport.written_messages) == 10

    @pytest.mark.anyio
    async def test_is_ready_transitions(self):
        """Test is_ready() state transitions."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()

        # Initially not ready
        assert not transport.is_ready()

        # Ready after connect
        await transport.connect()
        assert transport.is_ready()

        # Not ready after close
        await transport.close()
        assert not transport.is_ready()

        # Can reconnect
        await transport.connect()
        assert transport.is_ready()


# ============================================
# Async Iterator Streaming Tests
# ============================================


class TestAsyncIteratorStreaming:
    """Test AsyncIterator message streaming behavior."""

    @pytest.mark.anyio
    async def test_read_messages_streams_incrementally(self):
        """Test that messages are streamed incrementally, not batched."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()
        await transport.connect()

        # Queue one message at a time
        messages_to_send = ["msg1", "msg2", "msg3"]

        messages_read = []

        async def reader():
            async for msg in transport.read_messages():
                messages_read.append(msg)
                if len(messages_read) >= len(messages_to_send):
                    break

        async def sender():
            # Send messages with small delay
            for msg in messages_to_send:
                await anyio.sleep(0.01)
                transport.queue_message(msg)

        # Run reader and sender concurrently
        async with anyio.create_task_group() as tg:
            tg.start_soon(reader)
            tg.start_soon(sender)

        assert messages_read == messages_to_send

    @pytest.mark.anyio
    async def test_read_messages_async_iteration_protocol(self):
        """Test that read_messages() follows async iteration protocol."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()
        await transport.connect()

        transport.queue_message("test")

        # Manual async iteration
        iterator = transport.read_messages()
        msg = await iterator.__anext__()
        assert msg == "test"

    @pytest.mark.anyio
    async def test_read_messages_cancellation(self):
        """Test that read_messages() can be cancelled."""
        if Transport is None:
            pytest.skip("Transport not yet implemented")

        try:
            from tests.utils.mock_transport import MockTransport
        except ImportError:
            pytest.skip("MockTransport not yet implemented")

        transport = MockTransport()
        await transport.connect()

        messages_read = []

        # Start reading but cancel after short time
        try:
            with anyio.fail_after(0.1):
                async for msg in transport.read_messages():
                    messages_read.append(msg)
        except TimeoutError:
            pass  # Expected

        # Should have read 0 messages (none were queued)
        assert len(messages_read) == 0
