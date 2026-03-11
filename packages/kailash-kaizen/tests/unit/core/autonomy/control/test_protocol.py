"""
Tier 1 Unit Tests for ControlProtocol

Tests the ControlProtocol class including:
- Protocol initialization with transport
- Request/response pairing using anyio.Event
- Background message reader lifecycle
- Timeout handling with anyio.fail_after
- Multiple concurrent requests
- Error handling (transport failures, timeouts)
- Edge cases: unsolicited messages, duplicate responses, stop during request

Coverage Target: 100% for protocol layer
Test Strategy: TDD - Tests written BEFORE implementation
Infrastructure: MockTransport with in-memory queues

Design Principles from ADR-011:
- Use anyio.Event for request/response synchronization
- Use anyio.create_task_group for background tasks
- Use anyio.fail_after for timeout handling
- Thread-safe request tracking (dict[request_id, Event])
- Clean shutdown (cancel background tasks)
- Clear error messages (explicit is better than implicit)
"""

import json
from typing import Any

import anyio
import pytest

# Configure pytest for async tests
# Note: Uses asyncio backend only (see conftest.py) due to trio CancelScope compatibility
pytestmark = pytest.mark.anyio

# Import types
from kaizen.core.autonomy.control.types import ControlRequest, ControlResponse

# Import MockTransport
from tests.utils.mock_transport import MockTransport

# Import will work after implementation
try:
    from kaizen.core.autonomy.control.protocol import ControlProtocol
except ImportError:
    # Placeholder for TDD - tests will fail until implementation exists
    ControlProtocol = None


# ============================================
# Test Fixtures
# ============================================


@pytest.fixture
def transport():
    """Provide a fresh MockTransport for each test."""
    return MockTransport()


@pytest.fixture
async def connected_transport():
    """Provide a connected MockTransport."""
    transport = MockTransport()
    await transport.connect()
    return transport


@pytest.fixture
def sample_request() -> ControlRequest:
    """Create a sample ControlRequest."""
    return ControlRequest.create(
        type="question",
        data={"question": "Proceed with deletion?", "options": ["yes", "no"]},
    )


@pytest.fixture
def sample_response_data(sample_request: ControlRequest) -> dict[str, Any]:
    """Create sample response data matching the request."""
    return {
        "request_id": sample_request.request_id,
        "data": {"answer": "yes"},
        "error": None,
    }


# ============================================
# Initialization Tests
# ============================================


class TestProtocolInitialization:
    """Test ControlProtocol initialization."""

    def test_protocol_requires_transport(self):
        """Test that ControlProtocol requires a transport argument."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        transport = MockTransport()
        protocol = ControlProtocol(transport=transport)

        assert protocol is not None
        assert hasattr(protocol, "_transport")

    def test_protocol_initialization_sets_internal_state(self, transport):
        """Test that protocol initializes internal state correctly."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        protocol = ControlProtocol(transport=transport)

        # Should have request tracking dict
        assert hasattr(protocol, "_pending_requests")

        # Should start with no pending requests
        assert len(protocol._pending_requests) == 0

        # Should not have background task running yet
        assert hasattr(protocol, "_reader_task")
        assert protocol._reader_task is False

    def test_protocol_rejects_invalid_transport(self):
        """Test that protocol rejects non-Transport objects."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        # Should raise TypeError for invalid transport
        with pytest.raises(TypeError, match="transport must be a Transport instance"):
            ControlProtocol(transport="not a transport")


# ============================================
# Lifecycle Tests (start/stop)
# ============================================


class TestProtocolLifecycle:
    """Test ControlProtocol start/stop lifecycle."""

    async def test_protocol_start_connects_transport(self, transport):
        """Test that start() connects the transport."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        protocol = ControlProtocol(transport=transport)

        async with anyio.create_task_group() as tg:
            # Start protocol
            await protocol.start(tg)

            # Transport should be connected
            assert transport.is_ready()

            # Background reader should be running
            assert protocol._reader_task is True

            # Clean shutdown
            tg.cancel_scope.cancel()

    async def test_protocol_start_launches_background_reader(self, transport):
        """Test that start() launches the background message reader."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        protocol = ControlProtocol(transport=transport)

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Reader task should be tracked
            assert protocol._reader_task is True

            # Cancel for cleanup
            tg.cancel_scope.cancel()

    async def test_protocol_stop_gracefully_shuts_down(self, connected_transport):
        """Test that stop() gracefully shuts down the protocol."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        protocol = ControlProtocol(transport=connected_transport)

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Stop protocol
            await protocol.stop()

            # Transport should be closed
            assert not connected_transport.is_ready()

            # No pending requests
            assert len(protocol._pending_requests) == 0

    async def test_protocol_stop_is_idempotent(self, connected_transport):
        """Test that stop() can be called multiple times safely."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        protocol = ControlProtocol(transport=connected_transport)

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # First stop
            await protocol.stop()

            # Second stop should not raise
            await protocol.stop()

            # Transport should still be closed
            assert not connected_transport.is_ready()


# ============================================
# Request/Response Pairing Tests
# ============================================


class TestRequestResponsePairing:
    """Test send_request() and request/response pairing."""

    async def test_send_request_returns_response(
        self, connected_transport, sample_request, sample_response_data
    ):
        """Test that send_request() sends request and waits for response."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        protocol = ControlProtocol(transport=connected_transport)

        # Start protocol in background
        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Simulate transport receiving a response
            async def simulate_response():
                await anyio.sleep(0.1)  # Small delay
                response_json = json.dumps(sample_response_data)
                connected_transport.queue_message(response_json)

            tg.start_soon(simulate_response)

            # Send request and wait for response
            response = await protocol.send_request(sample_request, timeout=5.0)

            # Should receive correct response
            assert response is not None
            assert response.request_id == sample_request.request_id
            assert response.data == {"answer": "yes"}
            assert not response.is_error

            tg.cancel_scope.cancel()

    async def test_send_request_writes_to_transport(
        self, connected_transport, sample_request
    ):
        """Test that send_request() writes the request to transport."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        protocol = ControlProtocol(transport=connected_transport)

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Send request (will timeout, but we only care about write)
            async def send_and_timeout():
                try:
                    await protocol.send_request(sample_request, timeout=0.2)
                except TimeoutError:
                    pass  # Expected

            tg.start_soon(send_and_timeout)
            await anyio.sleep(0.3)  # Wait for timeout

            # Check that request was written
            written_messages = connected_transport.get_written_messages()
            assert len(written_messages) == 1

            # Parse and verify
            written_data = json.loads(written_messages[0])
            assert written_data["request_id"] == sample_request.request_id
            assert written_data["type"] == "question"

            tg.cancel_scope.cancel()

    async def test_send_request_pairs_response_by_request_id(self, connected_transport):
        """Test that responses are paired by request_id."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        protocol = ControlProtocol(transport=connected_transport)

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Create two requests
            request1 = ControlRequest.create("question", {"q": "First?"})
            request2 = ControlRequest.create("question", {"q": "Second?"})

            # Simulate responses arriving in REVERSE order
            async def simulate_responses():
                await anyio.sleep(0.1)

                # Send response for request2 FIRST
                response2_json = json.dumps(
                    {
                        "request_id": request2.request_id,
                        "data": {"answer": "second"},
                        "error": None,
                    }
                )
                connected_transport.queue_message(response2_json)

                await anyio.sleep(0.05)

                # Send response for request1 SECOND
                response1_json = json.dumps(
                    {
                        "request_id": request1.request_id,
                        "data": {"answer": "first"},
                        "error": None,
                    }
                )
                connected_transport.queue_message(response1_json)

            tg.start_soon(simulate_responses)

            # Send requests concurrently
            async def send_request1():
                resp = await protocol.send_request(request1, timeout=5.0)
                assert resp.data == {"answer": "first"}

            async def send_request2():
                resp = await protocol.send_request(request2, timeout=5.0)
                assert resp.data == {"answer": "second"}

            tg.start_soon(send_request1)
            tg.start_soon(send_request2)

            # Wait for both to complete
            await anyio.sleep(0.5)

            tg.cancel_scope.cancel()


# ============================================
# Timeout Tests
# ============================================


class TestTimeoutHandling:
    """Test timeout handling using anyio.fail_after."""

    async def test_send_request_timeout_raises_error(
        self, connected_transport, sample_request
    ):
        """Test that send_request() raises TimeoutError after timeout."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        protocol = ControlProtocol(transport=connected_transport)

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Send request with very short timeout, no response
            with pytest.raises(TimeoutError):
                await protocol.send_request(sample_request, timeout=0.1)

            tg.cancel_scope.cancel()

    async def test_send_request_default_timeout_is_60_seconds(
        self, connected_transport, sample_request
    ):
        """Test that default timeout is 60 seconds."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        protocol = ControlProtocol(transport=connected_transport)

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # This test would take too long, so we just verify the signature
            # In actual code, verify timeout parameter defaults to 60.0
            import inspect

            sig = inspect.signature(protocol.send_request)
            timeout_param = sig.parameters.get("timeout")

            assert timeout_param is not None
            assert timeout_param.default == 60.0

            tg.cancel_scope.cancel()

    async def test_send_request_cleans_up_on_timeout(
        self, connected_transport, sample_request
    ):
        """Test that pending request is cleaned up after timeout."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        protocol = ControlProtocol(transport=connected_transport)

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Send request with timeout
            try:
                await protocol.send_request(sample_request, timeout=0.1)
            except TimeoutError:
                pass  # Expected

            # Pending requests should be cleaned up
            assert sample_request.request_id not in protocol._pending_requests

            tg.cancel_scope.cancel()


# ============================================
# Concurrent Request Tests
# ============================================


class TestConcurrentRequests:
    """Test multiple concurrent requests."""

    async def test_multiple_concurrent_requests(self, connected_transport):
        """Test that protocol handles multiple concurrent requests correctly."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        protocol = ControlProtocol(transport=connected_transport)

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Create 5 requests
            requests = [
                ControlRequest.create("question", {"q": f"Question {i}?"})
                for i in range(5)
            ]

            # Simulate responses
            async def simulate_responses():
                await anyio.sleep(0.1)
                for req in requests:
                    response_json = json.dumps(
                        {
                            "request_id": req.request_id,
                            "data": {"answer": f"Answer for {req.data['q']}"},
                            "error": None,
                        }
                    )
                    connected_transport.queue_message(response_json)
                    await anyio.sleep(0.02)  # Small delay between responses

            tg.start_soon(simulate_responses)

            # Send all requests concurrently
            results = []

            async def send_and_collect(req):
                resp = await protocol.send_request(req, timeout=5.0)
                results.append(resp)

            for req in requests:
                tg.start_soon(send_and_collect, req)

            # Wait for all to complete
            await anyio.sleep(1.0)

            # Should have 5 responses
            assert len(results) == 5

            # All should be successful
            for resp in results:
                assert not resp.is_error
                assert "answer" in resp.data

            tg.cancel_scope.cancel()

    async def test_concurrent_requests_are_thread_safe(self, connected_transport):
        """Test that concurrent request tracking is thread-safe."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        protocol = ControlProtocol(transport=connected_transport)

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Create many requests to stress test thread safety
            num_requests = 20
            requests = [
                ControlRequest.create("question", {"q": f"Q{i}"})
                for i in range(num_requests)
            ]

            # Simulate responses in random order
            async def simulate_responses():
                await anyio.sleep(0.05)
                import random

                shuffled = requests.copy()
                random.shuffle(shuffled)

                for req in shuffled:
                    response_json = json.dumps(
                        {
                            "request_id": req.request_id,
                            "data": {"answer": "ok"},
                            "error": None,
                        }
                    )
                    connected_transport.queue_message(response_json)

            tg.start_soon(simulate_responses)

            # Send all requests concurrently
            results = []

            async def send_and_collect(req):
                resp = await protocol.send_request(req, timeout=5.0)
                results.append(resp)

            for req in requests:
                tg.start_soon(send_and_collect, req)

            # Wait for all
            await anyio.sleep(1.0)

            # All should succeed
            assert len(results) == num_requests

            tg.cancel_scope.cancel()


# ============================================
# Background Reader Tests
# ============================================


class TestBackgroundMessageReader:
    """Test the background _read_messages() task."""

    async def test_background_reader_processes_messages(
        self, connected_transport, sample_request, sample_response_data
    ):
        """Test that background reader processes incoming messages."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        protocol = ControlProtocol(transport=connected_transport)

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Queue response before sending request
            response_json = json.dumps(sample_response_data)
            connected_transport.queue_message(response_json)

            # Send request - should receive queued response
            response = await protocol.send_request(sample_request, timeout=1.0)

            assert response.request_id == sample_request.request_id

            tg.cancel_scope.cancel()

    async def test_background_reader_handles_transport_errors(
        self, connected_transport
    ):
        """Test that background reader handles transport errors gracefully."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        protocol = ControlProtocol(transport=connected_transport)

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Close transport to simulate error
            await connected_transport.close()

            # Background reader should handle this gracefully
            # and not crash the protocol
            await anyio.sleep(0.2)

            # Protocol should still be able to stop cleanly
            await protocol.stop()

            tg.cancel_scope.cancel()


# ============================================
# Error Handling Tests
# ============================================


class TestErrorHandling:
    """Test error handling in ControlProtocol."""

    async def test_send_request_handles_error_response(
        self, connected_transport, sample_request
    ):
        """Test that send_request() handles error responses."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        protocol = ControlProtocol(transport=connected_transport)

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Simulate error response
            async def simulate_error_response():
                await anyio.sleep(0.1)
                error_response = {
                    "request_id": sample_request.request_id,
                    "data": None,
                    "error": "User cancelled operation",
                }
                connected_transport.queue_message(json.dumps(error_response))

            tg.start_soon(simulate_error_response)

            # Send request
            response = await protocol.send_request(sample_request, timeout=5.0)

            # Should receive error response
            assert response.is_error
            assert response.error == "User cancelled operation"

            tg.cancel_scope.cancel()

    async def test_send_request_before_start_raises_error(
        self, transport, sample_request
    ):
        """Test that send_request() raises error if protocol not started."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        protocol = ControlProtocol(transport=transport)

        # Try to send request without starting protocol
        with pytest.raises(RuntimeError, match="Protocol not started"):
            await protocol.send_request(sample_request, timeout=5.0)

    async def test_send_request_handles_invalid_json_response(
        self, connected_transport, sample_request
    ):
        """Test that background reader handles invalid JSON gracefully."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        protocol = ControlProtocol(transport=connected_transport)

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Queue invalid JSON
            connected_transport.queue_message("not valid json {{{")

            # Queue valid response
            async def send_valid_response():
                await anyio.sleep(0.1)
                response_json = json.dumps(
                    {
                        "request_id": sample_request.request_id,
                        "data": {"answer": "yes"},
                        "error": None,
                    }
                )
                connected_transport.queue_message(response_json)

            tg.start_soon(send_valid_response)

            # Should skip invalid JSON and process valid response
            response = await protocol.send_request(sample_request, timeout=5.0)
            assert response.data == {"answer": "yes"}

            tg.cancel_scope.cancel()


# ============================================
# Edge Case Tests
# ============================================


class TestEdgeCases:
    """Test edge cases and corner scenarios."""

    async def test_unsolicited_message_is_ignored(
        self, connected_transport, sample_request
    ):
        """Test that unsolicited messages (no matching request) are ignored."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        protocol = ControlProtocol(transport=connected_transport)

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Queue unsolicited response
            unsolicited_response = {
                "request_id": "req_unknown",
                "data": {"unexpected": "data"},
                "error": None,
            }
            connected_transport.queue_message(json.dumps(unsolicited_response))

            # Queue expected response
            async def send_expected_response():
                await anyio.sleep(0.1)
                response_json = json.dumps(
                    {
                        "request_id": sample_request.request_id,
                        "data": {"answer": "yes"},
                        "error": None,
                    }
                )
                connected_transport.queue_message(response_json)

            tg.start_soon(send_expected_response)

            # Should receive expected response, ignoring unsolicited
            response = await protocol.send_request(sample_request, timeout=5.0)
            assert response.request_id == sample_request.request_id

            tg.cancel_scope.cancel()

    async def test_duplicate_response_for_same_request_id(
        self, connected_transport, sample_request
    ):
        """Test that duplicate responses are ignored after first one."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        protocol = ControlProtocol(transport=connected_transport)

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Simulate two responses for same request_id
            async def simulate_duplicate_responses():
                await anyio.sleep(0.1)

                # First response
                response1_json = json.dumps(
                    {
                        "request_id": sample_request.request_id,
                        "data": {"answer": "first"},
                        "error": None,
                    }
                )
                connected_transport.queue_message(response1_json)

                await anyio.sleep(0.05)

                # Duplicate response (should be ignored)
                response2_json = json.dumps(
                    {
                        "request_id": sample_request.request_id,
                        "data": {"answer": "second"},
                        "error": None,
                    }
                )
                connected_transport.queue_message(response2_json)

            tg.start_soon(simulate_duplicate_responses)

            # Should receive first response only
            response = await protocol.send_request(sample_request, timeout=5.0)
            assert response.data == {"answer": "first"}

            # Duplicate should have been ignored silently
            tg.cancel_scope.cancel()

    async def test_stop_during_pending_request(
        self, connected_transport, sample_request
    ):
        """Test that stop() during pending request cancels it gracefully."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        protocol = ControlProtocol(transport=connected_transport)

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Send request (no response will come)
            async def send_request_and_expect_cancel():
                try:
                    await protocol.send_request(sample_request, timeout=10.0)
                    pytest.fail("Should have been cancelled")
                except anyio.get_cancelled_exc_class():
                    pass  # Expected

            tg.start_soon(send_request_and_expect_cancel)

            # Wait a bit, then stop protocol
            await anyio.sleep(0.1)
            await protocol.stop()

            # Should clean up gracefully
            assert len(protocol._pending_requests) == 0

            tg.cancel_scope.cancel()

    async def test_response_with_missing_request_id_field(
        self, connected_transport, sample_request
    ):
        """Test that responses missing request_id are handled gracefully."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        protocol = ControlProtocol(transport=connected_transport)

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Queue malformed response (missing request_id)
            malformed_response = {
                "data": {"answer": "yes"},
                "error": None,
                # Missing: "request_id"
            }
            connected_transport.queue_message(json.dumps(malformed_response))

            # Queue valid response
            async def send_valid_response():
                await anyio.sleep(0.1)
                response_json = json.dumps(
                    {
                        "request_id": sample_request.request_id,
                        "data": {"answer": "yes"},
                        "error": None,
                    }
                )
                connected_transport.queue_message(response_json)

            tg.start_soon(send_valid_response)

            # Should skip malformed and process valid
            response = await protocol.send_request(sample_request, timeout=5.0)
            assert response.request_id == sample_request.request_id

            tg.cancel_scope.cancel()


# ============================================
# Integration Tests (with real MockTransport)
# ============================================


class TestProtocolIntegration:
    """Integration tests using MockTransport end-to-end."""

    async def test_full_request_response_cycle(self):
        """Test complete request/response cycle end-to-end."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        transport = MockTransport()
        await transport.connect()

        protocol = ControlProtocol(transport=transport)

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Create request
            request = ControlRequest.create(
                "approval", {"action": "delete_files", "count": 100}
            )

            # Simulate user responding
            async def simulate_user_response():
                await anyio.sleep(0.1)
                response = ControlResponse(
                    request_id=request.request_id,
                    data={"approved": True, "confirmation": "Deletion confirmed"},
                )
                transport.queue_message(response.to_json())

            tg.start_soon(simulate_user_response)

            # Send request and get response
            response = await protocol.send_request(request, timeout=5.0)

            # Verify response
            assert response.request_id == request.request_id
            assert response.data["approved"] is True
            assert response.data["confirmation"] == "Deletion confirmed"
            assert not response.is_error

            # Clean up
            await protocol.stop()
            tg.cancel_scope.cancel()

    async def test_protocol_handles_rapid_fire_requests(self):
        """Test protocol under rapid-fire request load."""
        if ControlProtocol is None:
            pytest.skip("ControlProtocol not yet implemented")

        transport = MockTransport()
        await transport.connect()

        protocol = ControlProtocol(transport=transport)

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            num_requests = 50
            requests = [
                ControlRequest.create("question", {"q": f"Question {i}?"})
                for i in range(num_requests)
            ]

            # Respond to all requests
            async def auto_responder():
                await anyio.sleep(0.05)
                for req in requests:
                    response = ControlResponse(
                        request_id=req.request_id,
                        data={"answer": f"Answer {req.data['q']}"},
                    )
                    transport.queue_message(response.to_json())

            tg.start_soon(auto_responder)

            # Send all requests rapidly
            results = []

            async def send_request(req):
                resp = await protocol.send_request(req, timeout=5.0)
                results.append(resp)

            for req in requests:
                tg.start_soon(send_request, req)

            # Wait for all to complete
            await anyio.sleep(2.0)

            # All should succeed
            assert len(results) == num_requests
            for resp in results:
                assert not resp.is_error

            await protocol.stop()
            tg.cancel_scope.cancel()
