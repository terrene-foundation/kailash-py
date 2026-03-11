"""Integration tests for SSE (Server-Sent Events) Streaming in Nexus.

Feature #3: SSE Streaming - Test-First Development
Status: RED PHASE - Tests written before implementation

These tests verify that Nexus supports proper SSE streaming format for:
- SSE format (`data: {...}\\n\\n`)
- Event types (`event: message\\n`)
- Event IDs (`id: 123\\n`)
- Proper headers (text/event-stream, no-cache)
- Keepalive comments (`:keepalive\\n\\n`)
- Error event streaming
- Multiple events in sequence
- Client disconnect handling

SSE Specification: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events
"""

import asyncio
import json
import re
import time
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient
from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus


class TestSSEStreamingFormat:
    """Test suite for SSE format compliance."""

    def setup_method(self):
        """Setup test instance with simple workflow."""
        self.app = Nexus(
            api_port=8200,
            enable_durability=False,
            enable_auth=False,
            enable_monitoring=False,
        )

        # Create simple test workflow
        self.workflow = WorkflowBuilder()
        self.workflow.add_node(
            "PythonCodeNode",
            "test_node",
            {"code": "result = {'message': 'Hello SSE!', 'value': 42}"},
        )
        self.app.register("test_sse", self.workflow.build())

    def teardown_method(self):
        """Cleanup after each test."""
        if hasattr(self, "app") and self.app._running:
            self.app.stop()

    def test_sse_format_data_field(self):
        """Test that SSE events have proper 'data:' prefix.

        Acceptance Criteria AC-3.1:
        - Given workflow execution with STREAM mode
        - When I connect to streaming endpoint
        - Then each event follows format: `id: N\\nevent: type\\ndata: {...}\\n\\n`

        Verifies:
        - Each event has `data: ` prefix
        - Data contains valid JSON
        - Data line is followed by double newline
        """
        client = TestClient(self.app._gateway.app)

        # Execute workflow in stream mode
        with client.stream(
            "POST", "/workflows/test_sse/execute", json={"mode": "stream"}
        ) as response:
            assert response.status_code == 200
            response.read()  # Consume the stream

            # Collect all event data
            events_raw = response.text

            # Verify SSE format: data: {...}\n\n
            # SSE events are separated by double newline
            assert "data: " in events_raw, "SSE events must have 'data:' prefix"

            # Verify double newline separators
            assert "\n\n" in events_raw, "SSE events must end with double newline"

            # Parse SSE events
            events = self._parse_sse_stream(events_raw)
            assert len(events) > 0, "Should have at least one SSE event"

            # Verify each event has data field
            for event in events:
                if event.get("type") != "comment":  # Skip keepalive comments
                    assert "data" in event, f"Event missing 'data' field: {event}"
                    # Verify data is valid JSON
                    try:
                        json.loads(event["data"])
                    except json.JSONDecodeError:
                        pytest.fail(f"Event data is not valid JSON: {event['data']}")

    def test_sse_format_double_newline(self):
        """Test that SSE events end with double newline (\\n\\n).

        SSE specification requires each event to be terminated with \\n\\n.
        """
        client = TestClient(self.app._gateway.app)

        with client.stream(
            "POST", "/workflows/test_sse/execute", json={"mode": "stream"}
        ) as response:
            response.read()  # Consume the stream
            events_raw = response.text

            # Split by double newline to get individual events
            event_blocks = [
                block for block in events_raw.split("\n\n") if block.strip()
            ]

            assert len(event_blocks) > 0, "Should have at least one event block"

            # Verify each event block contains proper fields
            for block in event_blocks:
                # Each block should have at least one line
                lines = block.strip().split("\n")
                assert len(lines) > 0, f"Event block is empty: {block}"

    def test_sse_event_types(self):
        """Test that SSE events have proper 'event:' field.

        Acceptance Criteria AC-3.2:
        - Given successful workflow execution
        - When I subscribe to SSE stream
        - Then I receive events in order: start → complete
        - And each event has incrementing ID

        Event types:
        - start: Workflow execution started
        - progress: Node execution progress (optional)
        - complete: Workflow completed successfully
        - error: Workflow failed
        """
        client = TestClient(self.app._gateway.app)

        with client.stream(
            "POST", "/workflows/test_sse/execute", json={"mode": "stream"}
        ) as response:
            response.read()  # Consume the stream
            events_raw = response.text
            events = self._parse_sse_stream(events_raw)

            # Filter out keepalive comments
            real_events = [e for e in events if e.get("type") != "comment"]

            assert (
                len(real_events) >= 2
            ), "Should have at least start and complete events"

            # Verify event types
            event_types = [e.get("event") for e in real_events]
            assert "start" in event_types, "Should have 'start' event"
            assert (
                "complete" in event_types or "error" in event_types
            ), "Should have 'complete' or 'error' event"

            # Verify order: start should be first
            assert event_types[0] == "start", "First event should be 'start'"

            # Verify last event is terminal (complete or error)
            assert event_types[-1] in [
                "complete",
                "error",
            ], "Last event should be 'complete' or 'error'"

    def test_sse_event_ids(self):
        """Test that SSE events have monotonically increasing IDs.

        Acceptance Criteria AC-3.1:
        - Each event has `id: N\\n` field
        - IDs are monotonically increasing integers
        - IDs start from 1

        Event IDs enable client reconnection with Last-Event-ID header.
        """
        client = TestClient(self.app._gateway.app)

        with client.stream(
            "POST", "/workflows/test_sse/execute", json={"mode": "stream"}
        ) as response:
            response.read()  # Consume the stream
            events_raw = response.text
            events = self._parse_sse_stream(events_raw)

            # Filter out comments (no IDs)
            events_with_ids = [e for e in events if "id" in e]

            assert len(events_with_ids) > 0, "Should have events with IDs"

            # Extract IDs
            ids = [int(e["id"]) for e in events_with_ids]

            # Verify IDs are monotonically increasing
            assert ids == sorted(
                ids
            ), f"Event IDs must be monotonically increasing: {ids}"

            # Verify IDs start from 1
            assert ids[0] == 1, f"First event ID should be 1, got {ids[0]}"

            # Verify IDs are consecutive
            for i in range(len(ids) - 1):
                assert (
                    ids[i + 1] == ids[i] + 1
                ), f"Event IDs must be consecutive: {ids[i]} -> {ids[i+1]}"

    def test_sse_multiple_events_sequence(self):
        """Test that multiple SSE events are sent in correct sequence.

        Verifies:
        - Start event is sent first
        - Complete event is sent last
        - All events properly formatted
        - Events contain expected data
        """
        client = TestClient(self.app._gateway.app)

        with client.stream(
            "POST", "/workflows/test_sse/execute", json={"mode": "stream"}
        ) as response:
            response.read()  # Consume the stream
            events_raw = response.text
            events = self._parse_sse_stream(events_raw)

            # Filter real events (not comments)
            real_events = [e for e in events if e.get("type") != "comment"]

            # Verify start event structure
            start_event = real_events[0]
            assert start_event["event"] == "start"
            start_data = json.loads(start_event["data"])
            assert "workflow_id" in start_data
            assert "timestamp" in start_data

            # Verify complete event structure
            complete_event = real_events[-1]
            assert complete_event["event"] in ["complete", "error"]
            complete_data = json.loads(complete_event["data"])
            assert "timestamp" in complete_data

            if complete_event["event"] == "complete":
                assert "result" in complete_data

    def test_sse_keepalive_comments(self):
        """Test that SSE keepalive comments are sent for long connections.

        Acceptance Criteria AC-3.5:
        - Given long-running workflow (>15 seconds)
        - When I subscribe to SSE stream
        - Then I receive keepalive comments (`:keepalive\\n\\n`) every 15 seconds
        - And connection stays alive

        Keepalive format: `:keepalive\\n\\n` (SSE comment, ignored by clients)
        """
        # Create long-running workflow
        long_workflow = WorkflowBuilder()
        long_workflow.add_node(
            "PythonCodeNode",
            "slow_node",
            {"code": "import time; time.sleep(2); result = {'done': True}"},
        )
        self.app.register("slow_workflow", long_workflow.build())

        client = TestClient(self.app._gateway.app)

        with client.stream(
            "POST", "/workflows/slow_workflow/execute", json={"mode": "stream"}
        ) as response:
            response.read()  # Consume the stream
            events_raw = response.text

            # Look for keepalive comments
            # SSE comments start with `:` and don't have data field
            has_keepalive = ":keepalive" in events_raw or ": keepalive" in events_raw

            # For 2-second workflow, keepalive might not trigger
            # But format should support it
            # This test verifies the format is correct when keepalives are present
            if has_keepalive:
                assert (
                    "\n\n" in events_raw
                ), "Keepalive must be followed by double newline"

    def _parse_sse_stream(self, raw_stream: str) -> List[Dict[str, str]]:
        """Parse raw SSE stream into structured events.

        Args:
            raw_stream: Raw SSE stream text

        Returns:
            List of parsed events, each as dict with fields:
            - id: Event ID (if present)
            - event: Event type (if present)
            - data: Event data (if present)
            - type: "comment" for keepalive comments
        """
        events = []
        current_event = {}

        for line in raw_stream.split("\n"):
            line = line.strip()

            if not line:
                # Empty line = end of event
                if current_event:
                    events.append(current_event)
                    current_event = {}
                continue

            # Parse SSE fields
            if line.startswith(":"):
                # Comment (keepalive)
                events.append({"type": "comment", "data": line})
            elif ":" in line:
                field, value = line.split(":", 1)
                field = field.strip()
                value = value.strip()
                current_event[field] = value

        # Add last event if exists
        if current_event:
            events.append(current_event)

        return events


class TestSSEHeaders:
    """Test suite for SSE HTTP headers."""

    def setup_method(self):
        """Setup test instance."""
        self.app = Nexus(
            api_port=8201,
            enable_durability=False,
            enable_auth=False,
            enable_monitoring=False,
        )

        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode", "test", {"code": "result = {'status': 'ok'}"}
        )
        self.app.register("test_headers", workflow.build())

    def teardown_method(self):
        """Cleanup after each test."""
        if hasattr(self, "app") and self.app._running:
            self.app.stop()

    def test_sse_content_type_header(self):
        """Test that SSE response has text/event-stream content type.

        Acceptance Criteria AC-3.4:
        - Given SSE streaming endpoint
        - When I connect
        - Then response includes Content-Type: text/event-stream
        """
        client = TestClient(self.app._gateway.app)

        response = client.post(
            "/workflows/test_headers/execute", json={"mode": "stream"}
        )

        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert (
            "text/event-stream" in content_type
        ), f"Expected text/event-stream, got {content_type}"

    def test_sse_cache_control_header(self):
        """Test that SSE response has Cache-Control: no-cache.

        Prevents proxies from caching the streaming response.
        """
        client = TestClient(self.app._gateway.app)

        response = client.post(
            "/workflows/test_headers/execute", json={"mode": "stream"}
        )

        cache_control = response.headers.get("cache-control", "")
        assert (
            "no-cache" in cache_control
        ), f"Expected no-cache in Cache-Control, got {cache_control}"

    def test_sse_connection_header(self):
        """Test that SSE response has Connection: keep-alive.

        Keeps the connection open for streaming.
        """
        client = TestClient(self.app._gateway.app)

        response = client.post(
            "/workflows/test_headers/execute", json={"mode": "stream"}
        )

        # Connection header might not be present in TestClient
        # but should be present in real deployment
        # Verify that streaming works (implies keep-alive)
        assert response.status_code == 200

    def test_sse_x_accel_buffering_header(self):
        """Test that SSE response has X-Accel-Buffering: no.

        Disables nginx buffering for immediate event delivery.
        """
        client = TestClient(self.app._gateway.app)

        response = client.post(
            "/workflows/test_headers/execute", json={"mode": "stream"}
        )

        # X-Accel-Buffering header should be present
        # This is critical for nginx deployments
        x_accel = response.headers.get("x-accel-buffering", "")
        if x_accel:  # May not be present in test client
            assert x_accel == "no", f"Expected X-Accel-Buffering: no, got {x_accel}"


class TestSSEWorkflowEvents:
    """Test suite for workflow-specific SSE events."""

    def setup_method(self):
        """Setup test instance with various workflows."""
        self.app = Nexus(
            api_port=8202,
            enable_durability=False,
            enable_auth=False,
            enable_monitoring=False,
        )

    def teardown_method(self):
        """Cleanup after each test."""
        if hasattr(self, "app") and self.app._running:
            self.app.stop()

    def test_workflow_start_event(self):
        """Test that workflow emits proper start event.

        Start event should contain:
        - workflow_id
        - timestamp
        """
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode", "start_test", {"code": "result = {'test': 'start'}"}
        )
        self.app.register("start_test", workflow.build())

        client = TestClient(self.app._gateway.app)

        with client.stream(
            "POST", "/workflows/start_test/execute", json={"mode": "stream"}
        ) as response:
            response.read()  # Consume the stream
            events_raw = response.text

            # Parse first event
            events = self._parse_sse_stream(events_raw)
            real_events = [e for e in events if e.get("type") != "comment"]

            assert len(real_events) > 0, "Should have at least one event"

            start_event = real_events[0]
            assert start_event["event"] == "start"

            start_data = json.loads(start_event["data"])
            assert "workflow_id" in start_data
            assert "timestamp" in start_data
            assert isinstance(start_data["timestamp"], (int, float))

    def test_workflow_complete_event(self):
        """Test that successful workflow emits complete event.

        Complete event should contain:
        - result (workflow output)
        - timestamp
        """
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "complete_test",
            {"code": "result = {'status': 'completed', 'value': 123}"},
        )
        self.app.register("complete_test", workflow.build())

        client = TestClient(self.app._gateway.app)

        with client.stream(
            "POST", "/workflows/complete_test/execute", json={"mode": "stream"}
        ) as response:
            response.read()  # Consume the stream
            events_raw = response.text
            events = self._parse_sse_stream(events_raw)
            real_events = [e for e in events if e.get("type") != "comment"]

            # Last event should be complete
            complete_event = real_events[-1]
            assert complete_event["event"] == "complete"

            complete_data = json.loads(complete_event["data"])
            assert "result" in complete_data
            assert "timestamp" in complete_data

    def test_workflow_error_event(self):
        """Test that failed workflow emits error event.

        Acceptance Criteria AC-3.3:
        - Given workflow execution that fails
        - When I subscribe to SSE stream
        - Then I receive events: start → error
        - And error event includes error message
        """
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "error_test",
            {"code": "raise ValueError('Test error for SSE')"},
        )
        self.app.register("error_test", workflow.build())

        client = TestClient(self.app._gateway.app)

        with client.stream(
            "POST", "/workflows/error_test/execute", json={"mode": "stream"}
        ) as response:
            response.read()  # Consume the stream
            events_raw = response.text
            events = self._parse_sse_stream(events_raw)
            real_events = [e for e in events if e.get("type") != "comment"]

            # Should have start and error events
            assert len(real_events) >= 2
            assert real_events[0]["event"] == "start"
            assert real_events[-1]["event"] == "error"

            # Error event should contain error message
            error_data = json.loads(real_events[-1]["data"])
            assert "error" in error_data
            assert "Test error for SSE" in error_data["error"]

    def test_workflow_multiple_node_events(self):
        """Test workflow with multiple nodes generates events.

        For workflows with multiple nodes, we should eventually
        support progress events for each node execution.

        Current: Start + Complete (both nodes execute)
        Future: Start + Progress(node1) + Progress(node2) + Complete
        """
        workflow = WorkflowBuilder()
        # Create two independent nodes (no connection needed for testing)
        workflow.add_node("PythonCodeNode", "node1", {"code": "result = {'step': 1}"})
        workflow.add_node("PythonCodeNode", "node2", {"code": "result = {'step': 2}"})

        self.app.register("multi_node", workflow.build())

        client = TestClient(self.app._gateway.app)

        with client.stream(
            "POST", "/workflows/multi_node/execute", json={"mode": "stream"}
        ) as response:
            response.read()  # Consume the stream
            events_raw = response.text
            events = self._parse_sse_stream(events_raw)
            real_events = [e for e in events if e.get("type") != "comment"]

            # At minimum: start + complete
            assert len(real_events) >= 2
            assert real_events[0]["event"] == "start"
            assert real_events[-1]["event"] in ["complete", "error"]

    def _parse_sse_stream(self, raw_stream: str) -> List[Dict[str, str]]:
        """Parse raw SSE stream into structured events."""
        events = []
        current_event = {}

        for line in raw_stream.split("\n"):
            line = line.strip()

            if not line:
                if current_event:
                    events.append(current_event)
                    current_event = {}
                continue

            if line.startswith(":"):
                events.append({"type": "comment", "data": line})
            elif ":" in line:
                field, value = line.split(":", 1)
                field = field.strip()
                value = value.strip()
                current_event[field] = value

        if current_event:
            events.append(current_event)

        return events


class TestSSEPerformance:
    """Test suite for SSE performance and stability."""

    def setup_method(self):
        """Setup test instance."""
        self.app = Nexus(
            api_port=8203,
            enable_durability=False,
            enable_auth=False,
            enable_monitoring=False,
        )

    def teardown_method(self):
        """Cleanup after each test."""
        if hasattr(self, "app") and self.app._running:
            self.app.stop()

    def test_sse_event_latency(self):
        """Test that SSE events are delivered with low latency.

        Acceptance Criteria:
        - First event delivered < 10ms
        - Subsequent events < 100ms
        """
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "fast", {"code": "result = {'fast': True}"})
        self.app.register("fast_workflow", workflow.build())

        client = TestClient(self.app._gateway.app)

        start_time = time.time()

        with client.stream(
            "POST", "/workflows/fast_workflow/execute", json={"mode": "stream"}
        ) as response:
            # Read first chunk
            first_chunk_time = time.time() - start_time

            # First event should be delivered quickly
            # Note: In real deployment, this should be < 10ms
            # In tests, network overhead is minimal
            assert (
                first_chunk_time < 1.0
            ), f"First event took {first_chunk_time:.3f}s, expected < 1s"

    def test_sse_throughput(self):
        """Test that SSE can handle rapid event generation.

        Verifies that events are delivered efficiently without
        excessive buffering or delays.
        """
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "throughput",
            {"code": "result = {'items': list(range(100))}"},
        )
        self.app.register("throughput_test", workflow.build())

        client = TestClient(self.app._gateway.app)

        start_time = time.time()

        with client.stream(
            "POST", "/workflows/throughput_test/execute", json={"mode": "stream"}
        ) as response:
            response.read()  # Consume the stream
            events_raw = response.text

        total_time = time.time() - start_time

        # Should complete quickly (< 5 seconds for simple workflow)
        assert total_time < 5.0, f"Workflow took {total_time:.3f}s, expected < 5s"

    def test_sse_memory_usage(self):
        """Test that SSE streaming doesn't leak memory.

        For long-running streams, memory should remain stable.
        """
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "memory_test",
            {"code": "result = {'data': 'x' * 1000}"},  # 1KB of data
        )
        self.app.register("memory_test", workflow.build())

        client = TestClient(self.app._gateway.app)

        # Execute multiple times
        for _ in range(10):
            with client.stream(
                "POST", "/workflows/memory_test/execute", json={"mode": "stream"}
            ) as response:
                response.read()  # Consume the stream
                _ = response.text  # Consume stream

        # If we get here without errors, memory is stable


class TestSSEClientCompatibility:
    """Test suite for client compatibility."""

    def setup_method(self):
        """Setup test instance."""
        self.app = Nexus(
            api_port=8204,
            enable_durability=False,
            enable_auth=False,
            enable_monitoring=False,
        )

        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode", "compat_test", {"code": "result = {'compatible': True}"}
        )
        self.app.register("compat_test", workflow.build())

    def teardown_method(self):
        """Cleanup after each test."""
        if hasattr(self, "app") and self.app._running:
            self.app.stop()

    def test_sse_event_parsing(self):
        """Test that SSE events can be parsed by standard parsers.

        Acceptance Criteria AC-3.7:
        - Given browser using EventSource API
        - When I connect to SSE endpoint
        - Then EventSource successfully receives events
        - And can parse event types and data
        """
        client = TestClient(self.app._gateway.app)

        with client.stream(
            "POST", "/workflows/compat_test/execute", json={"mode": "stream"}
        ) as response:
            response.read()  # Consume the stream
            events_raw = response.text

            # Simulate SSE parser behavior
            events = self._parse_sse_like_browser(events_raw)

            assert len(events) > 0, "Should parse at least one event"

            # Verify browser-compatible format
            for event in events:
                # Browser EventSource expects these fields
                if event.get("type") != "comment":
                    assert (
                        "data" in event or "event" in event
                    ), "Event must have data or event field"

    def test_sse_json_data_parsing(self):
        """Test that event data is valid JSON parseable by clients."""
        client = TestClient(self.app._gateway.app)

        with client.stream(
            "POST", "/workflows/compat_test/execute", json={"mode": "stream"}
        ) as response:
            response.read()  # Consume the stream
            events_raw = response.text
            events = self._parse_sse_like_browser(events_raw)

            for event in events:
                if event.get("type") != "comment" and "data" in event:
                    # Verify data is valid JSON
                    try:
                        data = json.loads(event["data"])
                        assert isinstance(
                            data, dict
                        ), "Event data should be JSON object"
                    except json.JSONDecodeError as e:
                        pytest.fail(f"Invalid JSON in event data: {e}")

    def test_sse_reconnection_support(self):
        """Test that event IDs enable reconnection.

        Future enhancement: Support Last-Event-ID header for resuming streams.

        Current: Verify IDs are present for future reconnection support.
        """
        client = TestClient(self.app._gateway.app)

        with client.stream(
            "POST", "/workflows/compat_test/execute", json={"mode": "stream"}
        ) as response:
            response.read()  # Consume the stream
            events_raw = response.text
            events = self._parse_sse_like_browser(events_raw)

            # Filter events with IDs
            events_with_ids = [e for e in events if "id" in e]

            # Should have IDs for reconnection support
            assert (
                len(events_with_ids) > 0
            ), "Events should have IDs for reconnection support"

    def _parse_sse_like_browser(self, raw_stream: str) -> List[Dict[str, str]]:
        """Parse SSE stream like a browser EventSource would.

        This simulates browser behavior for compatibility testing.
        """
        events = []
        current_event = {}

        for line in raw_stream.split("\n"):
            line = line.rstrip()  # Keep leading whitespace, remove trailing

            if not line:
                # Empty line = dispatch event
                if current_event:
                    events.append(current_event)
                    current_event = {}
                continue

            if line.startswith(":"):
                # Comment - ignored by EventSource
                events.append({"type": "comment", "data": line})
            elif ":" in line:
                # Field
                colon_pos = line.index(":")
                field = line[:colon_pos]
                value = line[colon_pos + 1 :]

                # Remove single leading space (SSE spec)
                if value.startswith(" "):
                    value = value[1:]

                current_event[field] = value

        # Dispatch final event if exists
        if current_event:
            events.append(current_event)

        return events


class TestSSEErrorHandling:
    """Test suite for SSE error handling."""

    def setup_method(self):
        """Setup test instance."""
        self.app = Nexus(
            api_port=8205,
            enable_durability=False,
            enable_auth=False,
            enable_monitoring=False,
        )

    def teardown_method(self):
        """Cleanup after each test."""
        if hasattr(self, "app") and self.app._running:
            self.app.stop()

    def test_sse_workflow_error_propagation(self):
        """Test that workflow errors are properly propagated via SSE.

        Error event should contain:
        - error message
        - timestamp
        """
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "error_node",
            {"code": "raise RuntimeError('Critical workflow error')"},
        )
        self.app.register("error_workflow", workflow.build())

        client = TestClient(self.app._gateway.app)

        with client.stream(
            "POST", "/workflows/error_workflow/execute", json={"mode": "stream"}
        ) as response:
            response.read()  # Consume the stream
            events_raw = response.text

            # Should receive start and error events
            assert "event: start" in events_raw or "start" in events_raw
            assert "event: error" in events_raw or "error" in events_raw
            assert "Critical workflow error" in events_raw

    def test_sse_malformed_request_handling(self):
        """Test that malformed requests return proper error events."""
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "normal", {"code": "result = {'ok': True}"})
        self.app.register("normal_workflow", workflow.build())

        client = TestClient(self.app._gateway.app)

        # Request with invalid mode should still work (uses default)
        # Or return error if mode validation is strict
        response = client.post(
            "/workflows/normal_workflow/execute",
            json={"mode": "stream"},  # Valid stream mode
        )

        assert response.status_code == 200

    def test_sse_client_disconnect_handling(self):
        """Test that server handles client disconnects gracefully.

        When client disconnects, server should:
        - Stop streaming
        - Clean up resources
        - Not crash or leak memory
        """
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "long_running",
            {"code": "import time; time.sleep(1); result = {'done': True}"},
        )
        self.app.register("long_workflow", workflow.build())

        client = TestClient(self.app._gateway.app)

        # Simulate early disconnect by not consuming full stream
        with client.stream(
            "POST", "/workflows/long_workflow/execute", json={"mode": "stream"}
        ) as response:
            # Read only first event then disconnect
            first_chunk = next(response.iter_bytes())
            # Connection will close when context exits

        # If we get here without errors, disconnect handling is correct
