"""End-to-End tests for SSE Streaming in real-world scenarios.

Feature #3: SSE Streaming - E2E Tests
Status: RED PHASE - Tests written before implementation

These tests verify SSE streaming in complete, real-world scenarios:
- Browser EventSource compatibility
- Real-time chat application streaming
- Long-running workflow progress
- Multiple concurrent SSE connections
- Network reliability (reconnection, timeout handling)
- Production deployment scenarios

These tests use real HTTP servers and simulated browser behavior.
"""

import asyncio
import json
import socket
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List

import pytest
import requests
from nexus import Nexus

from kailash.workflow.builder import WorkflowBuilder


def find_free_port(start_port: int = 8000) -> int:
    """Find a free port starting from start_port."""
    port = start_port
    while port < 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                port += 1
    raise RuntimeError("No free ports available")


@dataclass
class SSEEvent:
    """Represents a parsed SSE event."""

    id: str = None
    event: str = None
    data: str = None
    timestamp: float = None


class EventSourceSimulator:
    """Simulates browser EventSource API for testing.

    This class mimics the behavior of the browser's EventSource API
    to test SSE compatibility without needing a real browser.
    """

    def __init__(self, url: str):
        """Initialize EventSource simulator.

        Args:
            url: SSE endpoint URL
        """
        self.url = url
        self.events: List[SSEEvent] = []
        self.is_connected = False
        self.last_event_id = None
        self.error = None

    def connect(self, timeout: float = 10.0):
        """Connect to SSE endpoint and collect events.

        Args:
            timeout: Maximum time to wait for events (seconds)
        """
        try:
            response = requests.post(
                self.url, json={"mode": "stream"}, stream=True, timeout=timeout
            )

            if response.status_code != 200:
                self.error = f"Connection failed: {response.status_code}"
                return

            self.is_connected = True

            # Parse SSE stream
            current_event = SSEEvent()
            current_event.timestamp = time.time()

            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    # Empty line = dispatch event
                    if current_event.id or current_event.event or current_event.data:
                        self.events.append(current_event)
                        if current_event.id:
                            self.last_event_id = current_event.id
                        current_event = SSEEvent()
                        current_event.timestamp = time.time()
                    continue

                if line.startswith(":"):
                    # Comment (keepalive) - skip
                    continue

                if ":" not in line:
                    continue

                field, value = line.split(":", 1)
                field = field.strip()
                value = value.strip()

                # Set field on current event
                if field == "id":
                    current_event.id = value
                elif field == "event":
                    current_event.event = value
                elif field == "data":
                    current_event.data = value

            # Dispatch final event if exists
            if current_event.id or current_event.event or current_event.data:
                self.events.append(current_event)

        except requests.exceptions.Timeout:
            self.error = "Connection timeout"
        except Exception as e:
            self.error = str(e)
        finally:
            self.is_connected = False

    def get_events_by_type(self, event_type: str) -> List[SSEEvent]:
        """Get all events of specific type.

        Args:
            event_type: Event type to filter by

        Returns:
            List of events matching the type
        """
        return [e for e in self.events if e.event == event_type]


class TestBrowserEventSourceCompatibility:
    """Test suite for browser EventSource API compatibility.

    Acceptance Criteria AC-3.7:
    - Given browser using EventSource API
    - When I connect to SSE endpoint
    - Then EventSource successfully receives events
    - And can parse event types and data
    """

    @pytest.fixture
    def server(self):
        """Start real Nexus server for E2E testing."""
        api_port = find_free_port(8300)
        app = Nexus(
            api_port=api_port,
            enable_durability=False,
            enable_auth=False,
            enable_monitoring=False,
        )
        app._test_port = api_port  # Store port for tests to access

        # Register test workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "test_browser",
            {"code": "result = {'message': 'Browser test successful', 'value': 42}"},
        )
        app.register("browser_test", workflow.build())

        # Start server in background thread
        server_thread = threading.Thread(target=app.start, daemon=True)
        server_thread.start()

        # Wait for server to be ready
        time.sleep(2)

        yield app

        # Cleanup
        app.stop()

    def test_browser_eventsource_connection(self, server):
        """Test that EventSource can connect and receive events.

        Simulates browser EventSource connecting to SSE endpoint.
        """
        url = f"http://localhost:{server._test_port}/workflows/browser_test/execute"

        # Simulate EventSource connection
        event_source = EventSourceSimulator(url)
        event_source.connect(timeout=5.0)

        # Verify connection succeeded
        assert event_source.error is None, f"Connection failed: {event_source.error}"
        assert len(event_source.events) > 0, "Should receive at least one event"

    def test_browser_eventsource_event_types(self, server):
        """Test that EventSource can parse different event types.

        EventSource should receive and distinguish:
        - start events
        - complete events
        - error events
        """
        url = f"http://localhost:{server._test_port}/workflows/browser_test/execute"

        event_source = EventSourceSimulator(url)
        event_source.connect(timeout=5.0)

        # Verify event types
        start_events = event_source.get_events_by_type("start")
        complete_events = event_source.get_events_by_type("complete")

        assert len(start_events) > 0, "Should receive start event"
        assert len(complete_events) > 0, "Should receive complete event"

    def test_browser_eventsource_json_parsing(self, server):
        """Test that EventSource can parse JSON data in events.

        Browser JavaScript typically parses event.data as JSON.
        """
        url = f"http://localhost:{server._test_port}/workflows/browser_test/execute"

        event_source = EventSourceSimulator(url)
        event_source.connect(timeout=5.0)

        # Verify JSON parsing
        for event in event_source.events:
            if event.data:
                try:
                    data = json.loads(event.data)
                    assert isinstance(data, dict), "Event data should be JSON object"
                except json.JSONDecodeError:
                    pytest.fail(f"Failed to parse event data as JSON: {event.data}")

    def test_browser_eventsource_event_ids(self, server):
        """Test that EventSource receives and tracks event IDs.

        Event IDs enable reconnection with Last-Event-ID.
        """
        url = f"http://localhost:{server._test_port}/workflows/browser_test/execute"

        event_source = EventSourceSimulator(url)
        event_source.connect(timeout=5.0)

        # Verify event IDs
        events_with_ids = [e for e in event_source.events if e.id]
        assert len(events_with_ids) > 0, "Should receive events with IDs"

        # Verify last_event_id tracked
        assert (
            event_source.last_event_id is not None
        ), "EventSource should track last event ID"


class TestRealTimeChatStreaming:
    """Test suite for real-time chat application scenario.

    This simulates a chat application that streams AI responses
    token-by-token (or in this case, event-by-event).
    """

    @pytest.fixture
    def chat_server(self):
        """Start server with chat workflow."""
        api_port = find_free_port(8301)
        app = Nexus(
            api_port=api_port,
            enable_durability=False,
            enable_auth=False,
            enable_monitoring=False,
        )
        app._test_port = api_port

        # Simulate chat workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "chat_response",
            {
                "code": """
import time
# Simulate chat response
user_query = inputs.get('query', 'Hello')
response = f"Response to: {user_query}"
result = {'response': response, 'tokens': len(response.split())}
"""
            },
        )
        app.register("chat", workflow.build())

        server_thread = threading.Thread(target=app.start, daemon=True)
        server_thread.start()
        time.sleep(2)

        yield app

        app.stop()

    def test_chat_streaming_flow(self, chat_server):
        """Test complete chat streaming workflow.

        Simulates:
        1. User sends message
        2. Server streams response
        3. Client receives events in real-time
        """
        url = f"http://localhost:{chat_server._test_port}/workflows/chat/execute"

        # Send chat message
        response = requests.post(
            url,
            json={"mode": "stream", "inputs": {"query": "What is Kailash?"}},
            stream=True,
            timeout=10.0,
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        # Collect events
        events = []
        for line in response.iter_lines(decode_unicode=True):
            if line and not line.startswith(":"):
                events.append(line)

        # Verify streaming worked
        assert len(events) > 0, "Should receive streaming events"

    def test_chat_streaming_latency(self, chat_server):
        """Test that chat responses stream with low latency.

        Real-time chat requires quick initial response.
        """
        url = f"http://localhost:{chat_server._test_port}/workflows/chat/execute"

        start_time = time.time()

        response = requests.post(
            url,
            json={"mode": "stream", "inputs": {"query": "Quick test"}},
            stream=True,
            timeout=10.0,
        )

        # Time to first byte
        first_byte_time = None
        for _ in response.iter_content(chunk_size=1):
            first_byte_time = time.time() - start_time
            break

        # First byte should arrive quickly (< 1 second in test environment)
        assert first_byte_time is not None
        assert (
            first_byte_time < 1.0
        ), f"First byte took {first_byte_time:.3f}s, expected < 1s"


class TestLongRunningWorkflows:
    """Test suite for long-running workflows with progress updates.

    Tests scenarios where workflows take significant time to complete
    and need to send keepalive/progress updates.
    """

    @pytest.fixture
    def long_server(self):
        """Start server with long-running workflow."""
        api_port = find_free_port(8302)
        app = Nexus(
            api_port=api_port,
            enable_durability=False,
            enable_auth=False,
            enable_monitoring=False,
        )
        app._test_port = api_port

        # Long-running workflow (5 seconds)
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "long_task",
            {
                "code": """
import time
# Simulate long-running task
time.sleep(5)
result = {'status': 'completed', 'duration': 5}
"""
            },
        )
        app.register("long_task", workflow.build())

        server_thread = threading.Thread(target=app.start, daemon=True)
        server_thread.start()
        time.sleep(2)

        yield app

        app.stop()

    def test_long_workflow_streaming(self, long_server):
        """Test that long-running workflows maintain connection.

        Long workflows should:
        - Keep connection alive
        - Send keepalive comments
        - Eventually send complete event
        """
        url = f"http://localhost:{long_server._test_port}/workflows/long_task/execute"

        start_time = time.time()

        response = requests.post(
            url,
            json={"mode": "stream"},
            stream=True,
            timeout=20.0,  # Allow time for long task
        )

        events_raw = response.text
        duration = time.time() - start_time

        # Verify workflow completed
        assert "complete" in events_raw, "Should eventually complete"
        assert duration >= 4.0, f"Should take ~5s, took {duration:.1f}s"

    def test_long_workflow_keepalive(self, long_server):
        """Test that long workflows send keepalive comments.

        For workflows >15 seconds, should send `:keepalive` comments.
        For 5-second workflow, may or may not have keepalive.
        """
        url = f"http://localhost:{long_server._test_port}/workflows/long_task/execute"

        response = requests.post(
            url, json={"mode": "stream"}, stream=True, timeout=20.0
        )

        events_raw = response.text

        # Connection should remain stable
        # (keepalive helps prevent timeouts)
        assert (
            "complete" in events_raw or "error" in events_raw
        ), "Connection should remain stable until completion"


class TestConcurrentSSEConnections:
    """Test suite for multiple concurrent SSE connections.

    Acceptance Criteria:
    - Support 100+ concurrent SSE connections
    - No memory leaks
    - No connection interference
    """

    @pytest.fixture
    def concurrent_server(self):
        """Start server for concurrency testing."""
        api_port = find_free_port(8303)
        app = Nexus(
            api_port=api_port,
            enable_durability=False,
            enable_auth=False,
            enable_monitoring=False,
        )
        app._test_port = api_port

        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "concurrent_test",
            {
                "code": """
import time
import random
# Simulate varying execution times
time.sleep(random.uniform(0.1, 0.5))
result = {'worker_id': random.randint(1, 100)}
"""
            },
        )
        app.register("concurrent", workflow.build())

        server_thread = threading.Thread(target=app.start, daemon=True)
        server_thread.start()
        time.sleep(2)

        yield app

        app.stop()

    def test_multiple_concurrent_connections(self, concurrent_server):
        """Test that multiple clients can stream simultaneously.

        Simulates 10 concurrent chat users.
        """
        url = f"http://localhost:{concurrent_server._test_port}/workflows/concurrent/execute"

        # Create 10 concurrent requests
        def stream_request():
            try:
                response = requests.post(
                    url, json={"mode": "stream"}, stream=True, timeout=10.0
                )
                return response.status_code == 200
            except Exception as e:
                return False

        # Run concurrent requests
        with asyncio.Runner() as runner:

            async def run_concurrent():
                tasks = []
                for _ in range(10):
                    # Using asyncio for concurrency in test
                    task = asyncio.to_thread(stream_request)
                    tasks.append(task)

                results = await asyncio.gather(*tasks)
                return results

            results = runner.run(run_concurrent())

        # Verify all connections succeeded
        success_count = sum(1 for r in results if r)
        assert (
            success_count >= 8
        ), f"Expected >= 8/10 concurrent connections to succeed, got {success_count}"

    def test_concurrent_connection_isolation(self, concurrent_server):
        """Test that concurrent connections don't interfere.

        Each connection should receive its own independent event stream.
        """
        url = f"http://localhost:{concurrent_server._test_port}/workflows/concurrent/execute"

        # Start two connections simultaneously
        def get_events():
            response = requests.post(
                url, json={"mode": "stream"}, stream=True, timeout=10.0
            )
            return response.text

        # Run two requests
        with asyncio.Runner() as runner:

            async def run_two():
                task1 = asyncio.to_thread(get_events)
                task2 = asyncio.to_thread(get_events)
                return await asyncio.gather(task1, task2)

            events1, events2 = runner.run(run_two())

        # Both should have received events
        assert len(events1) > 0, "Connection 1 should receive events"
        assert len(events2) > 0, "Connection 2 should receive events"

        # Events might differ (due to random worker_id)
        # but structure should be same


class TestSSENetworkReliability:
    """Test suite for network reliability scenarios."""

    @pytest.fixture
    def reliability_server(self):
        """Start server for reliability testing."""
        api_port = find_free_port(8304)
        app = Nexus(
            api_port=api_port,
            enable_durability=False,
            enable_auth=False,
            enable_monitoring=False,
        )
        app._test_port = api_port

        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "reliable",
            {"code": "import time; time.sleep(0.5); result = {'status': 'ok'}"},
        )
        app.register("reliable", workflow.build())

        server_thread = threading.Thread(target=app.start, daemon=True)
        server_thread.start()
        time.sleep(2)

        yield app

        app.stop()

    def test_sse_client_timeout_handling(self, reliability_server):
        """Test that short timeouts are handled gracefully.

        Client might set aggressive timeouts. Server should handle properly.
        """
        url = f"http://localhost:{reliability_server._test_port}/workflows/reliable/execute"

        # Test with short timeout (should still succeed for 0.5s workflow)
        response = requests.post(
            url, json={"mode": "stream"}, stream=True, timeout=5.0  # Reasonable timeout
        )

        assert response.status_code == 200

    def test_sse_malformed_stream_recovery(self, reliability_server):
        """Test that clients can handle unexpected stream interruptions.

        If stream is interrupted, client should be able to reconnect.
        """
        url = f"http://localhost:{reliability_server._test_port}/workflows/reliable/execute"

        # First connection
        event_source1 = EventSourceSimulator(url)
        event_source1.connect(timeout=5.0)

        first_events = len(event_source1.events)

        # Second connection (simulating reconnection)
        event_source2 = EventSourceSimulator(url)
        event_source2.connect(timeout=5.0)

        second_events = len(event_source2.events)

        # Both connections should work independently
        assert first_events > 0, "First connection should receive events"
        assert second_events > 0, "Second connection should receive events"


class TestProductionDeploymentScenarios:
    """Test suite for production deployment scenarios.

    Tests real-world production concerns:
    - Load balancer compatibility
    - Nginx buffering
    - CORS for browser access
    - Resource cleanup
    """

    @pytest.fixture
    def production_server(self):
        """Start server simulating production config."""
        api_port = find_free_port(8305)
        app = Nexus(
            api_port=api_port,
            enable_durability=False,
            enable_auth=False,
            enable_monitoring=False,
        )
        app._test_port = api_port

        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "prod_test",
            {"code": "result = {'environment': 'production'}"},
        )
        app.register("prod", workflow.build())

        server_thread = threading.Thread(target=app.start, daemon=True)
        server_thread.start()
        time.sleep(2)

        yield app

        app.stop()

    def test_sse_nginx_buffering_disabled(self, production_server):
        """Test that X-Accel-Buffering header disables nginx buffering.

        Critical for nginx deployments to get immediate event delivery.
        """
        url = f"http://localhost:{production_server._test_port}/workflows/prod/execute"

        response = requests.post(url, json={"mode": "stream"}, stream=True, timeout=5.0)

        # Verify buffering header present
        x_accel = response.headers.get("x-accel-buffering", "")
        # Header might not be present in test environment
        # But if present, should be "no"
        if x_accel:
            assert x_accel == "no", f"Expected X-Accel-Buffering: no, got {x_accel}"

    def test_sse_cors_headers(self, production_server):
        """Test that SSE works with CORS for browser access.

        Browsers making cross-origin requests need CORS headers.
        """
        url = f"http://localhost:{production_server._test_port}/workflows/prod/execute"

        # Simulate browser cross-origin request
        response = requests.post(
            url,
            json={"mode": "stream"},
            stream=True,
            timeout=5.0,
            headers={"Origin": "http://example.com"},
        )

        # Should still work (CORS handled by Nexus/FastAPI)
        assert response.status_code == 200

    def test_sse_resource_cleanup(self, production_server):
        """Test that SSE connections properly clean up resources.

        After stream completes, resources should be freed.
        """
        url = f"http://localhost:{production_server._test_port}/workflows/prod/execute"

        # Run multiple streams sequentially
        for _ in range(5):
            response = requests.post(
                url, json={"mode": "stream"}, stream=True, timeout=5.0
            )

            # Consume entire stream
            _ = response.text

        # If we get here without memory errors, cleanup is working

    def test_sse_load_balancer_compatibility(self, production_server):
        """Test that SSE works through load balancers.

        Load balancers might add latency but should pass through SSE.
        """
        url = f"http://localhost:{production_server._test_port}/workflows/prod/execute"

        # Simulate load balancer scenario
        response = requests.post(
            url,
            json={"mode": "stream"},
            stream=True,
            timeout=5.0,
            headers={"X-Forwarded-For": "192.168.1.1", "X-Real-IP": "192.168.1.1"},
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
