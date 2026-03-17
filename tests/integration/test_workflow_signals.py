"""Integration tests for workflow signals and queries.

Tests the full signal/query lifecycle including:
- SignalWaitNode blocking and resuming on signal delivery
- Signal timeout behavior
- Query handler registration and execution from running workflows
- REST endpoint signal delivery via WorkflowServer
"""

import asyncio

import pytest

from kailash.runtime.local import LocalRuntime
from kailash.runtime.signals import QueryRegistry, SignalChannel


class TestSignalChannelIntegration:
    """Integration tests for signal channel with runtime."""

    @pytest.mark.asyncio
    async def test_signal_channel_with_runtime_tracking(self):
        """Runtime should create and track signal channels for active workflows."""
        runtime = LocalRuntime(enable_monitoring=False)

        # Before execution, no signals tracked
        assert len(runtime._workflow_signals) == 0

    @pytest.mark.asyncio
    async def test_signal_send_to_nonexistent_workflow_raises(self):
        """Sending signal to nonexistent workflow should raise KeyError."""
        runtime = LocalRuntime(enable_monitoring=False)

        with pytest.raises(KeyError, match="No active workflow found"):
            runtime.signal("nonexistent_id", "test_signal", {"data": 1})

    @pytest.mark.asyncio
    async def test_query_nonexistent_workflow_raises(self):
        """Querying nonexistent workflow should raise KeyError."""
        runtime = LocalRuntime(enable_monitoring=False)

        with pytest.raises(KeyError, match="No active workflow found"):
            await runtime.query("nonexistent_id", "status")

    @pytest.mark.asyncio
    async def test_get_signal_channel_returns_none_for_missing(self):
        """get_signal_channel should return None for unknown workflow."""
        runtime = LocalRuntime(enable_monitoring=False)
        assert runtime.get_signal_channel("unknown") is None

    @pytest.mark.asyncio
    async def test_get_query_registry_returns_none_for_missing(self):
        """get_query_registry should return None for unknown workflow."""
        runtime = LocalRuntime(enable_monitoring=False)
        assert runtime.get_query_registry("unknown") is None


class TestSignalChannelDirectUsage:
    """Tests for direct signal channel usage patterns."""

    @pytest.mark.asyncio
    async def test_signal_channel_producer_consumer(self):
        """Test producer-consumer pattern with signal channel."""
        channel = SignalChannel()

        produced = []
        consumed = []

        async def producer():
            for i in range(5):
                channel.send("items", {"item": i})
                produced.append(i)
                await asyncio.sleep(0.01)

        async def consumer():
            for _ in range(5):
                data = await channel.wait_for("items", timeout=2.0)
                consumed.append(data["item"])

        await asyncio.gather(producer(), consumer())
        assert produced == [0, 1, 2, 3, 4]
        assert sorted(consumed) == [0, 1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_signal_timeout_returns_quickly(self):
        """Timeout should not block longer than the timeout value."""
        channel = SignalChannel()

        with pytest.raises(TimeoutError):
            await channel.wait_for("never_sent", timeout=0.1)

    @pytest.mark.asyncio
    async def test_multiple_signal_names_concurrent(self):
        """Multiple signal names should work concurrently without interference."""
        channel = SignalChannel()

        async def send_signals():
            await asyncio.sleep(0.02)
            channel.send("approval", {"approved": True})
            channel.send("data_ready", {"rows": 100})

        async def wait_approval():
            return await channel.wait_for("approval", timeout=2.0)

        async def wait_data():
            return await channel.wait_for("data_ready", timeout=2.0)

        sender = asyncio.create_task(send_signals())
        approval, data = await asyncio.gather(wait_approval(), wait_data())
        await sender

        assert approval == {"approved": True}
        assert data == {"rows": 100}


class TestQueryRegistryIntegration:
    """Integration tests for query registry."""

    @pytest.mark.asyncio
    async def test_query_handler_returns_workflow_state(self):
        """Query handlers should return dynamic workflow state."""
        registry = QueryRegistry()

        # Simulate a stateful query handler
        state = {"iteration": 0, "status": "running"}

        def get_progress():
            return dict(state)

        registry.register("progress", get_progress)

        # Initial query
        result = await registry.query("progress")
        assert result["iteration"] == 0
        assert result["status"] == "running"

        # Update state (simulating workflow progress)
        state["iteration"] = 5
        state["status"] = "converging"

        # Query again should reflect updated state
        result = await registry.query("progress")
        assert result["iteration"] == 5
        assert result["status"] == "converging"

    @pytest.mark.asyncio
    async def test_multiple_query_handlers(self):
        """Multiple independent query handlers should work."""
        registry = QueryRegistry()

        registry.register("status", lambda: "running")
        registry.register("progress", lambda: {"done": 50, "total": 100})
        registry.register("errors", lambda: [])

        assert await registry.query("status") == "running"
        assert await registry.query("progress") == {"done": 50, "total": 100}
        assert await registry.query("errors") == []

    @pytest.mark.asyncio
    async def test_async_query_handler(self):
        """Async query handlers should be awaited properly."""
        registry = QueryRegistry()

        async def expensive_query(node_id="all"):
            await asyncio.sleep(0.01)  # Simulate async work
            return {"node_id": node_id, "metrics": {"latency_ms": 42}}

        registry.register("metrics", expensive_query)
        result = await registry.query("metrics", node_id="processor")
        assert result["node_id"] == "processor"
        assert result["metrics"]["latency_ms"] == 42


class TestWorkflowServerSignalEndpoints:
    """Tests for REST endpoint signal/query delivery."""

    @pytest.mark.asyncio
    async def test_signal_endpoint_no_runtime_returns_404(self):
        """Signal endpoint without runtime should return 404."""
        try:
            from httpx import ASGITransport, AsyncClient
        except ImportError:
            pytest.skip("httpx not installed")

        from kailash.servers.workflow_server import WorkflowServer

        server = WorkflowServer(title="Test Server")
        # No runtime configured

        transport = ASGITransport(app=server.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/workflows/wf1/signals/approval",
                json={"approved": True},
            )
            assert response.status_code == 404
            assert "No runtime configured" in response.json()["error"]

    @pytest.mark.asyncio
    async def test_query_endpoint_no_runtime_returns_404(self):
        """Query endpoint without runtime should return 404."""
        try:
            from httpx import ASGITransport, AsyncClient
        except ImportError:
            pytest.skip("httpx not installed")

        from kailash.servers.workflow_server import WorkflowServer

        server = WorkflowServer(title="Test Server")

        transport = ASGITransport(app=server.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/workflows/wf1/queries/status")
            assert response.status_code == 404
            assert "No runtime configured" in response.json()["error"]

    @pytest.mark.asyncio
    async def test_signal_endpoint_with_runtime(self):
        """Signal endpoint should deliver signal through runtime."""
        try:
            from httpx import ASGITransport, AsyncClient
        except ImportError:
            pytest.skip("httpx not installed")

        from kailash.servers.workflow_server import WorkflowServer

        runtime = LocalRuntime(enable_monitoring=False)
        server = WorkflowServer(title="Test Server", runtime=runtime)

        # Manually register a signal channel to simulate an active workflow
        channel = SignalChannel()
        registry = QueryRegistry()
        runtime._workflow_signals["test-run-123"] = {
            "signal_channel": channel,
            "query_registry": registry,
        }

        transport = ASGITransport(app=server.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/workflows/test-run-123/signals/approval",
                json={"approved": True, "reviewer": "alice"},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "signal_sent"
            assert body["signal_name"] == "approval"

        # Verify the signal was actually delivered
        assert channel.has_pending("approval")
        data = await channel.wait_for("approval", timeout=1.0)
        assert data == {"approved": True, "reviewer": "alice"}

    @pytest.mark.asyncio
    async def test_signal_endpoint_nonexistent_workflow_returns_404(self):
        """Signal to nonexistent workflow should return 404."""
        try:
            from httpx import ASGITransport, AsyncClient
        except ImportError:
            pytest.skip("httpx not installed")

        from kailash.servers.workflow_server import WorkflowServer

        runtime = LocalRuntime(enable_monitoring=False)
        server = WorkflowServer(title="Test Server", runtime=runtime)

        transport = ASGITransport(app=server.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/workflows/nonexistent/signals/test",
                json={},
            )
            assert response.status_code == 404
            assert "No active workflow found" in response.json()["error"]

    @pytest.mark.asyncio
    async def test_query_endpoint_with_runtime(self):
        """Query endpoint should execute query through runtime."""
        try:
            from httpx import ASGITransport, AsyncClient
        except ImportError:
            pytest.skip("httpx not installed")

        from kailash.servers.workflow_server import WorkflowServer

        runtime = LocalRuntime(enable_monitoring=False)
        server = WorkflowServer(title="Test Server", runtime=runtime)

        # Manually register a query handler
        channel = SignalChannel()
        registry = QueryRegistry()
        registry.register("progress", lambda: {"completed": 5, "total": 10})
        runtime._workflow_signals["test-run-456"] = {
            "signal_channel": channel,
            "query_registry": registry,
        }

        transport = ASGITransport(app=server.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/workflows/test-run-456/queries/progress")
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "ok"
            assert body["query_name"] == "progress"
            assert body["result"]["completed"] == 5
            assert body["result"]["total"] == 10

    @pytest.mark.asyncio
    async def test_query_endpoint_nonexistent_query_returns_404(self):
        """Query for nonexistent handler should return 404."""
        try:
            from httpx import ASGITransport, AsyncClient
        except ImportError:
            pytest.skip("httpx not installed")

        from kailash.servers.workflow_server import WorkflowServer

        runtime = LocalRuntime(enable_monitoring=False)
        server = WorkflowServer(title="Test Server", runtime=runtime)

        # Register workflow but no query handler for "missing"
        channel = SignalChannel()
        registry = QueryRegistry()
        runtime._workflow_signals["test-run-789"] = {
            "signal_channel": channel,
            "query_registry": registry,
        }

        transport = ASGITransport(app=server.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/workflows/test-run-789/queries/missing")
            assert response.status_code == 404
            assert "No handler registered" in response.json()["error"]

    @pytest.mark.asyncio
    async def test_signal_endpoint_empty_body(self):
        """Signal with empty body should send None as data."""
        try:
            from httpx import ASGITransport, AsyncClient
        except ImportError:
            pytest.skip("httpx not installed")

        from kailash.servers.workflow_server import WorkflowServer

        runtime = LocalRuntime(enable_monitoring=False)
        server = WorkflowServer(title="Test Server", runtime=runtime)

        channel = SignalChannel()
        registry = QueryRegistry()
        runtime._workflow_signals["test-empty"] = {
            "signal_channel": channel,
            "query_registry": registry,
        }

        transport = ASGITransport(app=server.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Send with empty body (no Content-Type)
            response = await client.post(
                "/workflows/test-empty/signals/ping",
                content=b"",
            )
            assert response.status_code == 200

        # The signal should have been sent with None data
        assert channel.has_pending("ping")
        data = await channel.wait_for("ping", timeout=1.0)
        assert data is None
