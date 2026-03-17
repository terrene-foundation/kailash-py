"""Unit tests for TODO-029: API Gateway real implementations."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from kailash.api.gateway import (
    WorkflowAPIGateway,
    WorkflowOrchestrator,
    WorkflowRegistration,
)


def _make_mock_workflow(name="test_wf"):
    """Create a MagicMock that passes Pydantic isinstance check for Workflow."""
    from kailash.workflow import Workflow

    wf = MagicMock(spec=Workflow)
    wf.name = name
    wf.workflow_id = f"wf-{name}"
    wf.nodes = {}
    wf.connections = []
    return wf


@pytest.fixture
def gateway():
    """Create a WorkflowAPIGateway for testing."""
    return WorkflowAPIGateway(
        title="Test Gateway",
        description="Test",
        version="1.0.0",
    )


@pytest.fixture
def test_client(gateway):
    """Create a FastAPI test client."""
    return TestClient(gateway.app)


def _register_embedded(gateway, name, wf=None):
    """Register an embedded workflow, bypassing WorkflowAPI creation."""
    if wf is None:
        wf = _make_mock_workflow(name)

    # Directly insert into the workflows dict (bypassing WorkflowAPI mount)
    gateway.workflows[name] = WorkflowRegistration(
        name=name,
        type="embedded",
        workflow=wf,
        description=name,
        version="1.0.0",
        tags=[],
    )
    return wf


class TestHealthCheck:
    def test_embedded_workflow_healthy(self, gateway, test_client):
        """Embedded workflows should always report healthy."""
        _register_embedded(gateway, "test")

        resp = test_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["workflows"]["test"] == "healthy"

    def test_proxy_health_check_unreachable(self, gateway, test_client):
        """Proxied workflow health check shows unreachable when backend is down."""
        gateway.proxy_workflow("remote", "http://nonexistent:9999")

        resp = test_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["workflows"]["remote"] in ("unreachable", "unhealthy")

    def test_mcp_health_check(self, gateway, test_client):
        """MCP server health check should report status."""
        mock_server = MagicMock()
        mock_server.ping.return_value = True
        gateway.register_mcp_server("tools", mock_server)

        resp = test_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mcp_servers"]["tools"] == "healthy"

    def test_mcp_health_unknown(self, gateway, test_client):
        """MCP server without ping/health reports unknown."""
        mock_server = MagicMock(spec=[])  # No ping or health method
        gateway.register_mcp_server("basic", mock_server)

        resp = test_client.get("/health")
        data = resp.json()
        assert data["mcp_servers"]["basic"] == "unknown"


class TestWebSocketSubscription:
    def test_websocket_subscribe(self, gateway, test_client):
        """WebSocket subscribe should acknowledge."""
        _register_embedded(gateway, "wf1")

        with test_client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe", "workflow": "wf1"})
            resp = ws.receive_json()
            assert resp["type"] == "subscribed"
            assert resp["workflow"] == "wf1"

    def test_websocket_subscribe_nonexistent(self, gateway, test_client):
        """Subscribe to nonexistent workflow should return error."""
        with test_client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe", "workflow": "nope"})
            resp = ws.receive_json()
            assert resp["type"] == "error"

    def test_websocket_unsubscribe(self, gateway, test_client):
        _register_embedded(gateway, "wf1")

        with test_client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe", "workflow": "wf1"})
            ws.receive_json()  # subscribed
            ws.send_json({"type": "unsubscribe", "workflow": "wf1"})
            resp = ws.receive_json()
            assert resp["type"] == "unsubscribed"

    def test_websocket_ack_other_messages(self, gateway, test_client):
        with test_client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "ping"})
            resp = ws.receive_json()
            assert resp["type"] == "ack"


class TestProxyRouting:
    def test_proxy_workflow_registration(self, gateway):
        gateway.proxy_workflow("remote", "http://backend:8080")
        assert "remote" in gateway.workflows
        assert gateway.workflows["remote"].type == "proxied"

    def test_proxy_duplicate_raises(self, gateway):
        gateway.proxy_workflow("remote", "http://backend:8080")
        with pytest.raises(ValueError, match="already registered"):
            gateway.proxy_workflow("remote", "http://other:8080")

    def test_proxy_multi_backend(self, gateway):
        """Comma-separated URLs should be split into multiple backends."""
        gateway.proxy_workflow("multi", "http://backend1:8080,http://backend2:8080")
        assert gateway.workflows["multi"].proxy_url == "http://backend1:8080"


class TestMCPToolEndpoints:
    def test_list_mcp_tools(self, gateway, test_client):
        mock_server = MagicMock()
        mock_server.list_tools.return_value = [
            {"name": "search", "description": "Search tool"}
        ]
        gateway.register_mcp_server("search_server", mock_server)

        resp = test_client.get("/mcp/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert "search_server" in data

    def test_call_mcp_tool(self, gateway, test_client):
        mock_server = MagicMock()
        mock_server.call_tool.return_value = {"result": "found"}
        gateway.register_mcp_server("tools", mock_server)

        resp = test_client.post(
            "/mcp/tools/tools/search",
            json={"query": "test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_call_mcp_tool_not_found(self, gateway, test_client):
        resp = test_client.post(
            "/mcp/nonexistent/tools/search",
            json={},
        )
        assert resp.status_code == 404

    def test_mcp_server_duplicate_raises(self, gateway):
        gateway.register_mcp_server("srv", MagicMock())
        with pytest.raises(ValueError, match="already registered"):
            gateway.register_mcp_server("srv", MagicMock())


class TestWorkflowOrchestrator:
    def test_create_chain_validates_workflows(self, gateway):
        orchestrator = WorkflowOrchestrator(gateway)
        with pytest.raises(ValueError, match="not registered"):
            orchestrator.create_chain("chain1", ["nonexistent"])

    def test_create_chain_success(self, gateway):
        _register_embedded(gateway, "wf1")

        orchestrator = WorkflowOrchestrator(gateway)
        orchestrator.create_chain("chain1", ["wf1"])
        assert "chain1" in orchestrator.chains

    @pytest.mark.asyncio
    async def test_execute_chain_not_found(self, gateway):
        orchestrator = WorkflowOrchestrator(gateway)
        with pytest.raises(ValueError, match="not found"):
            await orchestrator.execute_chain("nonexistent", {})

    @pytest.mark.asyncio
    async def test_execute_chain_embedded(self, gateway):
        """Chain execution with embedded workflow uses LocalRuntime."""
        _register_embedded(gateway, "wf1")

        orchestrator = WorkflowOrchestrator(gateway)
        orchestrator.create_chain("chain1", ["wf1"])

        with patch("kailash.api.gateway.LocalRuntime") as mock_runtime_cls:
            mock_runtime = MagicMock()
            mock_runtime.execute.return_value = (
                {"node1": {"key": "value"}},
                "run-123",
            )
            mock_runtime_cls.return_value = mock_runtime

            result = await orchestrator.execute_chain("chain1", {"input": "data"})

        assert result == {"key": "value"}


class TestRootEndpoints:
    def test_root(self, test_client):
        resp = test_client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test Gateway"

    def test_list_workflows(self, gateway, test_client):
        _register_embedded(gateway, "test")

        resp = test_client.get("/workflows")
        assert resp.status_code == 200
        data = resp.json()
        assert "test" in data


class TestPublishWorkflowEvent:
    @pytest.mark.asyncio
    async def test_publish_to_subscribers(self, gateway):
        queue = asyncio.Queue()
        gateway._ws_subscriptions["wf1"].add(queue)

        await gateway.publish_workflow_event("wf1", {"msg": "hello"})
        event = queue.get_nowait()
        assert event["msg"] == "hello"

    @pytest.mark.asyncio
    async def test_publish_no_subscribers(self, gateway):
        # Should not raise
        await gateway.publish_workflow_event("wf1", {"msg": "no one listening"})
