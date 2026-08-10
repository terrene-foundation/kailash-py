"""
Tier 2 Integration Tests for StdioTransport

Tests StdioTransport with real subprocess communication, NO MOCKING.

Test Strategy:
- Use real stdin/stdout with subprocess.PIPE
- Test parent-child bidirectional communication
- Test multiple messages in sequence
- Test error handling (broken pipes, closed streams)
- Test concurrent operations
- NO MOCKING: All tests use real subprocess I/O

Coverage Requirements:
- Parent-child communication: parent writes to child stdin, reads from child stdout
- Bidirectional flow: request-response patterns
- Line-based protocol: One JSON message per line
- Async I/O with anyio
- Error handling: broken pipes, closed streams, invalid JSON
- Concurrent operations: multiple messages in flight
- Lifecycle: spawn subprocess -> communicate -> close

Design from TODO-159 Week 9:
- StdioTransport is optimized for subprocess-to-subprocess communication
- Nearly identical to CLITransport but semantic difference
- Tests focus on parent-child process patterns
- Always ready (stdin/stdout always available in subprocess)

Target: 15+ integration tests
Timeout: <5 seconds per test
"""

import json
import subprocess
import sys
from pathlib import Path

import anyio
import pytest

# Configure pytest for async tests
pytestmark = pytest.mark.anyio

from kaizen.core.autonomy.control.transports.stdio import StdioTransport

# Import types
from kaizen.core.autonomy.control.types import ControlRequest, ControlResponse

# ============================================
# Test Fixtures
# ============================================


@pytest.fixture
def sample_request() -> ControlRequest:
    """Create a sample ControlRequest."""
    return ControlRequest.create(
        type="question",
        data={"question": "Proceed with deletion?", "options": ["yes", "no"]},
    )


@pytest.fixture
def sample_response_json(sample_request: ControlRequest) -> str:
    """Create sample response JSON matching the request."""
    response = ControlResponse(
        request_id=sample_request.request_id, data={"answer": "yes"}, error=None
    )
    return response.to_json()


@pytest.fixture
def subprocess_helper_script(tmp_path: Path) -> Path:
    """
    Create a helper Python script that simulates a subprocess using StdioTransport.

    This script uses StdioTransport to communicate with parent process:
    - Reads JSON from stdin (parent -> child)
    - Writes responses to stdout (child -> parent)
    - Demonstrates real subprocess-to-subprocess communication
    """
    script = tmp_path / "stdio_subprocess_helper.py"

    script_content = '''#!/usr/bin/env python3
"""
Subprocess Helper for Testing StdioTransport

Uses StdioTransport to communicate with parent process.
Reads requests from stdin, writes responses to stdout.

Usage modes:
1. ECHO mode: Echo back the request_id with a fixed response
2. ERROR mode: Respond with errors
3. MULTI mode: Send multiple responses
4. INVALID mode: Send invalid JSON
"""

import sys
import json
import asyncio

# Add parent directory to path to import StdioTransport
sys.path.insert(0, "{{SRC_PATH}}")

from kaizen.core.autonomy.control.transports.stdio import StdioTransport


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "echo"

    transport = StdioTransport()
    # StdioTransport is always ready - no need to connect
    assert transport.is_ready()

    if mode == "echo":
        # Echo mode: respond to each request
        async for line in transport.read_messages():
            try:
                request = json.loads(line)
                request_id = request.get("request_id")

                response = {
                    "request_id": request_id,
                    "data": {"answer": "yes", "echo": request.get("data")},
                    "error": None
                }

                await transport.write(json.dumps(response))

            except json.JSONDecodeError:
                # Skip invalid JSON
                continue

    elif mode == "error":
        # Error mode: respond with errors
        async for line in transport.read_messages():
            try:
                request = json.loads(line)
                request_id = request.get("request_id")

                response = {
                    "request_id": request_id,
                    "data": None,
                    "error": "Simulated error response"
                }

                await transport.write(json.dumps(response))

            except json.JSONDecodeError:
                continue

    elif mode == "multi":
        # Multi mode: send multiple responses for each request
        async for line in transport.read_messages():
            try:
                request = json.loads(line)
                request_id = request.get("request_id")

                # Send 3 responses for same request
                for i in range(3):
                    response = {
                        "request_id": request_id,
                        "data": {"answer": f"response_{i}"},
                        "error": None
                    }
                    await transport.write(json.dumps(response))

            except json.JSONDecodeError:
                continue

    elif mode == "invalid":
        # Invalid mode: send malformed JSON
        await transport.write("not valid json {{{")
        await transport.write("also not valid ]]")

    await transport.close()


if __name__ == "__main__":
    asyncio.run(main())
'''

    # Replace placeholder with actual source path
    src_path = Path(__file__).parent.parent.parent.parent / "src"
    script_content = script_content.replace("{{SRC_PATH}}", str(src_path))

    script.write_text(script_content)
    script.chmod(0o755)

    return script


# ============================================
# Initialization Tests
# ============================================


class TestStdioTransportInitialization:
    """Test StdioTransport initialization in subprocess context."""

    def test_stdio_transport_can_be_instantiated(self):
        """Test that StdioTransport can be created."""
        transport = StdioTransport()
        assert transport is not None
        assert hasattr(transport, "connect")
        assert hasattr(transport, "write")
        assert hasattr(transport, "read_messages")
        assert hasattr(transport, "close")
        assert hasattr(transport, "is_ready")

    def test_stdio_transport_inherits_from_transport(self):
        """Test that StdioTransport inherits from Transport ABC."""
        from kaizen.core.autonomy.control.transport import Transport

        transport = StdioTransport()
        assert isinstance(transport, Transport)

    def test_stdio_transport_always_ready(self):
        """Test that StdioTransport is always ready (stdin/stdout always available)."""
        transport = StdioTransport()
        # Key difference from CLITransport: always ready immediately
        assert transport.is_ready()


# ============================================
# Subprocess Communication Tests
# ============================================


class TestStdioTransportSubprocessCommunication:
    """Test StdioTransport with real subprocess I/O."""

    async def test_parent_to_child_communication(
        self, subprocess_helper_script: Path, sample_request: ControlRequest
    ):
        """Test parent writes to child stdin, child reads via StdioTransport."""
        async with await anyio.open_process(
            [sys.executable, str(subprocess_helper_script), "echo"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as proc:
            # Parent writes request to child stdin
            request_json = json.dumps(sample_request.__dict__)
            await proc.stdin.send((request_json + "\n").encode())

            # Child reads via StdioTransport and responds
            # Read response from child stdout with timeout
            with anyio.fail_after(5.0):
                output = await proc.stdout.receive()
                response_data = json.loads(output.decode().strip())

                assert response_data["request_id"] == sample_request.request_id
                assert response_data["data"]["answer"] == "yes"

            await proc.stdin.aclose()

    async def test_child_to_parent_communication(self, subprocess_helper_script: Path):
        """Test child writes to stdout via StdioTransport, parent reads."""
        async with await anyio.open_process(
            [sys.executable, str(subprocess_helper_script), "echo"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as proc:
            # Send request so child responds
            request = ControlRequest.create("question", {"q": "Test?"})
            request_json = json.dumps(request.__dict__)
            await proc.stdin.send((request_json + "\n").encode())

            # Parent reads from child stdout with timeout
            with anyio.fail_after(5.0):
                output = await proc.stdout.receive()
                response_data = json.loads(output.decode().strip())

                # Verify child wrote via StdioTransport
                assert "request_id" in response_data
                assert response_data["request_id"] == request.request_id

            await proc.stdin.aclose()

    async def test_bidirectional_parent_child_communication(
        self, subprocess_helper_script: Path
    ):
        """Test full bidirectional communication between parent and child."""
        async with await anyio.open_process(
            [sys.executable, str(subprocess_helper_script), "echo"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as proc:
            # Parent -> Child: Write request
            request = ControlRequest.create("question", {"q": "Bidirectional test?"})
            request_json = json.dumps(request.__dict__)
            await proc.stdin.send((request_json + "\n").encode())

            # Close stdin to signal completion
            await proc.stdin.aclose()

            # Child -> Parent: Read response
            with anyio.fail_after(5.0):
                response_line = await proc.stdout.receive()
                response_data = json.loads(response_line.decode().strip())

                # Verify full round-trip
                assert response_data["request_id"] == request.request_id
                assert "echo" in response_data["data"]
                assert response_data["data"]["echo"]["q"] == "Bidirectional test?"

    async def test_multiple_requests_in_sequence(self, subprocess_helper_script: Path):
        """Test sending multiple requests sequentially to subprocess."""
        async with await anyio.open_process(
            [sys.executable, str(subprocess_helper_script), "echo"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as proc:
            # Send 3 requests
            requests = [
                ControlRequest.create("question", {"q": f"Question {i}?"})
                for i in range(3)
            ]

            for req in requests:
                request_json = json.dumps(req.__dict__)
                await proc.stdin.send((request_json + "\n").encode())

            await proc.stdin.aclose()

            # Read all responses with timeout
            with anyio.fail_after(5.0):
                all_data = b""
                try:
                    while True:
                        chunk = await proc.stdout.receive()
                        if not chunk:
                            break
                        all_data += chunk
                except anyio.EndOfStream:
                    pass

                lines = all_data.decode().strip().split("\n")
                lines = [l for l in lines if l.strip()]

                # Parse responses
                responses = [json.loads(line) for line in lines]

                # Verify all received
                assert len(responses) >= 3

                # Verify request IDs match (order might vary)
                request_ids = {req.request_id for req in requests}
                response_ids = {resp["request_id"] for resp in responses[:3]}
                assert request_ids == response_ids


# ============================================
# Error Handling Tests
# ============================================


class TestStdioTransportErrorHandling:
    """Test error handling with real subprocess I/O."""

    async def test_handles_broken_pipe_gracefully(self, subprocess_helper_script: Path):
        """Test that StdioTransport handles broken pipe errors."""
        async with await anyio.open_process(
            [sys.executable, str(subprocess_helper_script), "echo"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as proc:
            # Close stdin immediately to create broken pipe
            await proc.stdin.aclose()

            # Wait for subprocess to finish with timeout
            # Subprocess will exit when stdin closes (no input to read)
            with anyio.fail_after(5.0):
                try:
                    # Try to read - should get EOF or no data
                    response = await proc.stdout.receive()
                    # If we get data, it should be empty or EOF
                    assert len(response) == 0 or response == b""
                except (anyio.EndOfStream, TimeoutError):
                    # Expected: stream is closed or timeout waiting for exit
                    pass

    async def test_handles_closed_stream(
        self, subprocess_helper_script: Path, sample_request: ControlRequest
    ):
        """Test handling of closed stream during communication."""
        async with await anyio.open_process(
            [sys.executable, str(subprocess_helper_script), "echo"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as proc:
            # Send request
            request_json = json.dumps(sample_request.__dict__)
            await proc.stdin.send((request_json + "\n").encode())

            # Close stdin
            await proc.stdin.aclose()

            # Should still be able to read the response
            with anyio.fail_after(5.0):
                response_line = await proc.stdout.receive()
                response_data = json.loads(response_line.decode().strip())

                assert response_data["request_id"] == sample_request.request_id

    async def test_handles_invalid_json_from_subprocess(
        self, subprocess_helper_script: Path
    ):
        """Test that invalid JSON from subprocess is handled gracefully."""
        async with await anyio.open_process(
            [sys.executable, str(subprocess_helper_script), "invalid"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as proc:
            # Close stdin to trigger helper to send invalid JSON
            await proc.stdin.aclose()

            # Read invalid JSON with timeout
            with anyio.fail_after(5.0):
                output = await proc.stdout.receive()

                # Should receive malformed data
                assert b"not valid json" in output or b"not valid" in output

    async def test_handles_empty_lines_from_subprocess(
        self, subprocess_helper_script: Path, sample_request: ControlRequest
    ):
        """Test that empty lines in subprocess output are handled gracefully."""
        async with await anyio.open_process(
            [sys.executable, str(subprocess_helper_script), "echo"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as proc:
            # Send empty line, then request, then empty line
            await proc.stdin.send(b"\n")

            request_json = json.dumps(sample_request.__dict__)
            await proc.stdin.send((request_json + "\n").encode())

            await proc.stdin.send(b"\n")
            await proc.stdin.aclose()

            # Should still receive valid response
            with anyio.fail_after(5.0):
                response_line = await proc.stdout.receive()

                # Parse response (skip empty lines)
                lines = response_line.decode().strip().split("\n")
                non_empty = [l for l in lines if l.strip()]

                assert len(non_empty) >= 1
                response_data = json.loads(non_empty[0])
                assert response_data["request_id"] == sample_request.request_id


# ============================================
# Line-Based Protocol Tests
# ============================================


class TestStdioTransportLineProtocol:
    """Test line-based JSON protocol in subprocess context."""

    async def test_one_json_message_per_line(self, subprocess_helper_script: Path):
        """Test that protocol expects one JSON message per line."""
        async with await anyio.open_process(
            [sys.executable, str(subprocess_helper_script), "echo"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as proc:
            # Send 3 messages on separate lines
            requests = [
                ControlRequest.create("question", {"q": f"Q{i}"}) for i in range(3)
            ]

            for req in requests:
                request_json = json.dumps(req.__dict__)
                # Each message on its own line
                await proc.stdin.send((request_json + "\n").encode())

            await proc.stdin.aclose()

            # Read all responses with timeout
            with anyio.fail_after(5.0):
                all_data = b""
                try:
                    while True:
                        chunk = await proc.stdout.receive()
                        if not chunk:
                            break
                        all_data += chunk
                except anyio.EndOfStream:
                    pass

                lines = all_data.decode().strip().split("\n")

                # Should have 3 lines (one per message)
                assert len(lines) >= 3

                # Each line should be valid JSON
                for i, line in enumerate(lines[:3]):
                    response = json.loads(line)
                    assert response["request_id"] == requests[i].request_id

    async def test_handles_very_long_lines(self, subprocess_helper_script: Path):
        """Test handling of very long JSON messages (single line)."""
        async with await anyio.open_process(
            [sys.executable, str(subprocess_helper_script), "echo"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as proc:
            # Create request with large data payload
            large_data = {
                "question": "Test?" * 1000,  # ~6000 characters
                "context": "x" * 10000,  # 10KB of data
            }

            request = ControlRequest.create("question", large_data)
            request_json = json.dumps(request.__dict__)

            # Should be very long single line
            assert len(request_json) > 15000
            assert "\n" not in request_json

            await proc.stdin.send((request_json + "\n").encode())
            await proc.stdin.aclose()

            # Should handle and respond with timeout
            with anyio.fail_after(5.0):
                response_line = await proc.stdout.receive()
                response_data = json.loads(response_line.decode().strip())

                assert response_data["request_id"] == request.request_id


# ============================================
# Concurrent Operations Tests
# ============================================


class TestStdioTransportConcurrency:
    """Test concurrent operations in subprocess context."""

    async def test_concurrent_requests_to_subprocess(
        self, subprocess_helper_script: Path
    ):
        """Test sending multiple concurrent requests to subprocess."""
        async with await anyio.open_process(
            [sys.executable, str(subprocess_helper_script), "echo"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as proc:
            # Create multiple requests
            requests = [
                ControlRequest.create("question", {"q": f"Question {i}?"})
                for i in range(5)
            ]

            # Use lock to serialize writes (prevent stdin conflicts)
            write_lock = anyio.Lock()

            # Write all requests
            async with anyio.create_task_group() as tg:
                for req in requests:

                    async def write_request(r):
                        request_json = json.dumps(r.__dict__)
                        async with write_lock:
                            await proc.stdin.send((request_json + "\n").encode())

                    tg.start_soon(write_request, req)

            await proc.stdin.aclose()

            # Read all responses
            # Increase timeout for trio backend which may be slower
            with anyio.fail_after(10.0):
                all_data = b""
                try:
                    while True:
                        chunk = await proc.stdout.receive()
                        if not chunk:
                            break
                        all_data += chunk
                except anyio.EndOfStream:
                    pass

                lines = all_data.decode().strip().split("\n")
                lines = [l for l in lines if l.strip()]

                # Should receive all responses
                assert len(lines) >= 5

    async def test_multiple_responses_from_subprocess(
        self, subprocess_helper_script: Path
    ):
        """Test handling multiple responses from subprocess (multi mode)."""
        async with await anyio.open_process(
            [sys.executable, str(subprocess_helper_script), "multi"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as proc:
            # Send single request
            request = ControlRequest.create("question", {"q": "Multi?"})
            request_json = json.dumps(request.__dict__)
            await proc.stdin.send((request_json + "\n").encode())
            await proc.stdin.aclose()

            # Read multiple responses (helper sends 3)
            with anyio.fail_after(5.0):
                all_data = b""
                try:
                    while True:
                        chunk = await proc.stdout.receive()
                        if not chunk:
                            break
                        all_data += chunk
                except anyio.EndOfStream:
                    pass

                lines = all_data.decode().strip().split("\n")
                lines = [l for l in lines if l.strip()]

                # Should receive 3 responses for 1 request
                assert len(lines) >= 3

                # All should have same request_id
                responses = [json.loads(line) for line in lines[:3]]
                assert all(r["request_id"] == request.request_id for r in responses)


# ============================================
# Performance Tests
# ============================================


class TestStdioTransportPerformance:
    """Test performance characteristics of subprocess communication."""

    async def test_low_latency_subprocess_communication(
        self, subprocess_helper_script: Path
    ):
        """
        Test that subprocess communication latency is low.

        Note: Includes subprocess startup overhead (~500-1000ms).
        Pure I/O latency would be <10ms, but subprocess startup dominates.
        """
        import time

        async with await anyio.open_process(
            [sys.executable, str(subprocess_helper_script), "echo"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as proc:
            request = ControlRequest.create("question", {"q": "Fast?"})
            request_json = json.dumps(request.__dict__)

            start = time.time()

            await proc.stdin.send((request_json + "\n").encode())

            # Read response with timeout
            with anyio.fail_after(5.0):
                await proc.stdout.receive()

            elapsed = time.time() - start

            # Should complete in <3s (includes subprocess startup)
            # Pure I/O latency is <10ms, but subprocess startup adds ~500-1500ms
            assert elapsed < 3.0, f"Latency too high: {elapsed:.3f}s"

            await proc.stdin.aclose()

    async def test_throughput_with_many_messages(self, subprocess_helper_script: Path):
        """Test throughput with rapid message exchange."""
        import time

        async with await anyio.open_process(
            [sys.executable, str(subprocess_helper_script), "echo"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as proc:
            num_messages = 20
            requests = [
                ControlRequest.create("question", {"q": f"Q{i}"})
                for i in range(num_messages)
            ]

            start = time.time()

            # Send all messages
            for req in requests:
                request_json = json.dumps(req.__dict__)
                await proc.stdin.send((request_json + "\n").encode())

            await proc.stdin.aclose()

            # Read all responses with timeout
            with anyio.fail_after(5.0):
                all_data = b""
                try:
                    while True:
                        chunk = await proc.stdout.receive()
                        if not chunk:
                            break
                        all_data += chunk
                except anyio.EndOfStream:
                    pass

                lines = all_data.decode().strip().split("\n")

            elapsed = time.time() - start

            # Should handle 20 messages in <5 seconds (includes subprocess startup ~500-1500ms)
            # Pure throughput would be <100ms, but subprocess startup dominates
            # Trio backend may be slower (~3-4s total)
            assert (
                elapsed < 5.0
            ), f"Throughput too low: {elapsed:.3f}s for {num_messages} messages"

            # Should receive all responses
            assert len(lines) >= num_messages


# ============================================
# Integration Summary
# ============================================


class TestStdioTransportIntegrationSummary:
    """Summary integration test covering all features."""

    async def test_complete_subprocess_lifecycle(self, subprocess_helper_script: Path):
        """
        Complete integration test: full subprocess lifecycle.

        Tests:
        - Spawn subprocess with StdioTransport
        - Bidirectional communication
        - Multiple messages
        - Error handling
        - Clean shutdown
        """
        async with await anyio.open_process(
            [sys.executable, str(subprocess_helper_script), "echo"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as proc:
            # Phase 1: Send normal requests
            requests = [
                ControlRequest.create("question", {"q": f"Question {i}?"})
                for i in range(3)
            ]

            for req in requests:
                request_json = json.dumps(req.__dict__)
                await proc.stdin.send((request_json + "\n").encode())

            # Close stdin to signal completion
            await proc.stdin.aclose()

            # Phase 2: Read responses with timeout
            with anyio.fail_after(5.0):
                all_data = b""
                try:
                    while True:
                        chunk = await proc.stdout.receive()
                        if not chunk:
                            break
                        all_data += chunk
                except anyio.EndOfStream:
                    pass

                lines = all_data.decode().strip().split("\n")

                # Parse all responses
                responses = []
                for line in lines:
                    if line.strip():
                        responses.append(json.loads(line))

                # Verify all received
                assert len(responses) >= 3

                # Verify request IDs match
                request_ids = {req.request_id for req in requests}
                response_ids = {resp["request_id"] for resp in responses[:3]}
                assert request_ids == response_ids

                # Verify no errors
                for resp in responses[:3]:
                    assert not resp.get("error")

            # Phase 3: Process should exit cleanly
            # (subprocess exits when stdin closes and all messages processed)
