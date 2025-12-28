"""Comprehensive unit tests for api_channel module."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from kailash.channels.api_channel import APIChannel
from kailash.channels.base import ChannelConfig, ChannelStatus, ChannelType
from kailash.servers import EnterpriseWorkflowServer
from kailash.workflow.graph import Workflow


class TestAPIChannel:
    """Test APIChannel class."""

    @pytest.fixture
    def channel_config(self):
        """Create channel configuration."""
        return ChannelConfig(
            name="test_api",
            channel_type=ChannelType.API,
            host="localhost",
            port=8080,
            enable_sessions=True,
            enable_auth=False,
            enable_event_routing=True,
            extra_config={
                "title": "Test API Server",
                "description": "Test API Description",
                "cors_origins": ["http://localhost:3000"],
                "enable_durability": True,
                "enable_resource_management": True,
            },
        )

    @pytest.fixture
    def mock_workflow_server(self):
        """Create mock workflow server."""
        server = Mock(spec=EnterpriseWorkflowServer)
        server.app = Mock()
        server.workflows = {}
        server.runtime = Mock()
        server.enable_durability = True
        server.enable_resource_management = True
        server.enable_async_execution = True
        server.enable_health_checks = True
        return server

    @pytest.fixture
    def api_channel(self, channel_config, mock_workflow_server):
        """Create APIChannel instance."""
        return APIChannel(channel_config, workflow_server=mock_workflow_server)

    def test_init_with_provided_server(self, channel_config, mock_workflow_server):
        """Test initialization with provided workflow server."""
        channel = APIChannel(channel_config, workflow_server=mock_workflow_server)

        assert channel.workflow_server is mock_workflow_server
        assert channel.app is mock_workflow_server.app
        assert channel.name == "test_api"
        assert channel.config is channel_config

    def test_init_without_server(self, channel_config):
        """Test initialization without provided workflow server."""
        with patch.object(APIChannel, "_create_workflow_server") as mock_create:
            mock_server = Mock(spec=EnterpriseWorkflowServer)
            mock_server.app = Mock()
            mock_create.return_value = mock_server

            channel = APIChannel(channel_config)

            mock_create.assert_called_once()
            assert channel.workflow_server is mock_server

    def test_create_workflow_server(self, channel_config):
        """Test workflow server creation."""
        with patch(
            "kailash.channels.api_channel.EnterpriseWorkflowServer"
        ) as mock_server_class:
            mock_server = Mock()
            mock_server.app = Mock()
            mock_server_class.return_value = mock_server

            channel = APIChannel(channel_config)

            mock_server_class.assert_called_once_with(
                title="Test API Server",
                description="Test API Description",
                cors_origins=["http://localhost:3000"],
                enable_durability=True,
                enable_resource_management=True,
                enable_async_execution=True,
                enable_health_checks=True,
            )

    def test_setup_channel_endpoints(self, api_channel):
        """Test that channel endpoints are set up."""
        # Verify that endpoints were added to the app
        assert api_channel.app is not None
        # The actual endpoints are added to the FastAPI app during initialization

    @pytest.mark.asyncio
    async def test_start_channel(self, api_channel):
        """Test starting the API channel."""
        api_channel.status = ChannelStatus.STOPPED

        with (
            patch.object(api_channel, "_setup_event_queue"),
            patch.object(api_channel, "emit_event") as mock_emit,
            patch("kailash.channels.api_channel.uvicorn") as mock_uvicorn,
        ):

            mock_server = Mock()
            mock_server.serve = AsyncMock()
            mock_uvicorn.Server.return_value = mock_server
            mock_uvicorn.Config.return_value = Mock()

            await api_channel.start()

            assert api_channel.status == ChannelStatus.RUNNING
            assert api_channel._server is mock_server
            mock_emit.assert_called()

    @pytest.mark.asyncio
    async def test_start_already_running(self, api_channel):
        """Test starting channel when already running."""
        api_channel.status = ChannelStatus.RUNNING

        await api_channel.start()

        # Should return without error
        assert api_channel.status == ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_with_error(self, api_channel):
        """Test starting channel with error."""
        api_channel.status = ChannelStatus.STOPPED

        with patch.object(
            api_channel, "_setup_event_queue", side_effect=Exception("Test error")
        ):
            with pytest.raises(Exception, match="Test error"):
                await api_channel.start()

            assert api_channel.status == ChannelStatus.ERROR

    @pytest.mark.asyncio
    async def test_stop_channel(self, api_channel):
        """Test stopping the API channel."""
        api_channel.status = ChannelStatus.RUNNING
        mock_server = Mock()

        # Create a task that will be cancelled
        async def dummy_task():
            await asyncio.sleep(1)

        task = asyncio.create_task(dummy_task())

        api_channel._server = mock_server
        api_channel._server_task = task

        with (
            patch.object(api_channel, "emit_event") as mock_emit,
            patch.object(api_channel, "_cleanup") as mock_cleanup,
        ):

            await api_channel.stop()

            assert api_channel.status == ChannelStatus.STOPPED
            assert mock_server.should_exit is True
            # Note: cancel is called within the stop method
            mock_emit.assert_called()
            mock_cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_already_stopped(self, api_channel):
        """Test stopping channel when already stopped."""
        api_channel.status = ChannelStatus.STOPPED

        await api_channel.stop()

        # Should return without error
        assert api_channel.status == ChannelStatus.STOPPED

    @pytest.mark.asyncio
    async def test_stop_with_error(self, api_channel):
        """Test stopping channel with error."""
        api_channel.status = ChannelStatus.RUNNING

        with patch.object(
            api_channel, "emit_event", side_effect=Exception("Test error")
        ):
            with pytest.raises(Exception, match="Test error"):
                await api_channel.stop()

            assert api_channel.status == ChannelStatus.ERROR

    @pytest.mark.asyncio
    async def test_handle_request_missing_workflow_name(self, api_channel):
        """Test handling request without workflow name."""
        request = {"inputs": {"test": "value"}}

        response = await api_channel.handle_request(request)

        assert response.success is False
        assert "workflow_name is required" in response.error

    @pytest.mark.asyncio
    async def test_handle_request_workflow_not_found(self, api_channel):
        """Test handling request for non-existent workflow."""
        request = {"workflow_name": "nonexistent", "inputs": {}}
        api_channel.workflow_server.workflows = {}

        response = await api_channel.handle_request(request)

        assert response.success is False
        assert "not found" in response.error

    @pytest.mark.asyncio
    async def test_handle_request_embedded_workflow_success(self, api_channel):
        """Test successful execution of embedded workflow."""
        mock_workflow = Mock(spec=Workflow)
        mock_registration = Mock()
        mock_registration.type = "embedded"
        mock_registration.workflow = mock_workflow

        api_channel.workflow_server.workflows = {"test_workflow": mock_registration}
        api_channel.workflow_server.runtime.execute.return_value = (
            {"result": "success"},
            "run_123",
        )

        request = {
            "workflow_name": "test_workflow",
            "inputs": {"param": "value"},
            "session_id": "session_123",
        }

        with patch.object(api_channel, "emit_event") as mock_emit:
            response = await api_channel.handle_request(request)

        assert response.success is True
        assert response.data["results"] == {"result": "success"}
        assert response.data["run_id"] == "run_123"
        assert response.data["workflow_name"] == "test_workflow"

        # Verify events were emitted
        assert mock_emit.call_count == 2  # request and completion events

    @pytest.mark.asyncio
    async def test_handle_request_proxied_workflow(self, api_channel):
        """Test handling proxied workflow request."""
        mock_registration = Mock()
        mock_registration.type = "proxied"

        api_channel.workflow_server.workflows = {"proxied_workflow": mock_registration}

        request = {"workflow_name": "proxied_workflow", "inputs": {}}

        response = await api_channel.handle_request(request)

        assert response.success is False
        assert "not yet supported" in response.error

    @pytest.mark.asyncio
    async def test_handle_request_with_exception(self, api_channel):
        """Test handling request with exception."""
        mock_workflow = Mock(spec=Workflow)
        mock_registration = Mock()
        mock_registration.type = "embedded"
        mock_registration.workflow = mock_workflow

        api_channel.workflow_server.workflows = {"test_workflow": mock_registration}
        api_channel.workflow_server.runtime.execute.side_effect = Exception(
            "Execution failed"
        )

        request = {"workflow_name": "test_workflow", "inputs": {}}

        with patch.object(api_channel, "emit_event") as mock_emit:
            response = await api_channel.handle_request(request)

        assert response.success is False
        assert "Execution failed" in response.error

        # Verify error event was emitted
        mock_emit.assert_called()

    def test_register_workflow(self, api_channel):
        """Test registering workflow."""
        mock_workflow = Mock(spec=Workflow)

        api_channel.register_workflow(
            name="test_workflow",
            workflow=mock_workflow,
            description="Test workflow",
            tags=["test"],
        )

        api_channel.workflow_server.register_workflow.assert_called_once_with(
            name="test_workflow",
            workflow=mock_workflow,
            description="Test workflow",
            tags=["test"],
        )

    def test_proxy_workflow(self, api_channel):
        """Test registering proxied workflow."""
        api_channel.proxy_workflow(
            name="proxied_workflow",
            proxy_url="http://external:8080",
            health_check="/health",
            description="Proxied workflow",
            tags=["proxy"],
        )

        api_channel.workflow_server.proxy_workflow.assert_called_once_with(
            name="proxied_workflow",
            proxy_url="http://external:8080",
            health_check="/health",
            description="Proxied workflow",
            tags=["proxy"],
        )

    @pytest.mark.asyncio
    async def test_health_check(self, api_channel):
        """Test health check."""
        api_channel._server = Mock()
        api_channel._server_task = Mock()
        api_channel._server_task.done.return_value = False
        api_channel.workflow_server.workflows = {
            "workflow1": Mock(),
            "workflow2": Mock(),
        }

        with patch.object(
            api_channel, "health_check", wraps=api_channel.health_check
        ) as mock_super:
            # Mock the super() call
            with patch("kailash.channels.api_channel.super") as mock_super_call:
                mock_super_health = AsyncMock(
                    return_value={"healthy": True, "checks": {"base": True}}
                )
                mock_super_call.return_value.health_check = mock_super_health

                health = await api_channel.health_check()

        assert health["healthy"] is True
        assert "server_running" in health["checks"]
        assert "workflows_registered" in health["checks"]
        assert "enterprise_features" in health["checks"]
        assert len(health["workflows"]) == 2


class TestAPIChannelEndpoints:
    """Test API channel endpoints."""

    @pytest.fixture
    def channel_config(self):
        """Create channel configuration."""
        return ChannelConfig(
            name="test_api", channel_type=ChannelType.API, host="localhost", port=8080
        )

    @pytest.fixture
    def mock_workflow_server(self):
        """Create mock workflow server."""
        from fastapi import FastAPI

        server = Mock(spec=EnterpriseWorkflowServer)
        server.app = FastAPI()
        server.workflows = {}
        server.runtime = Mock()
        server.enable_durability = True
        server.enable_resource_management = True
        server.enable_async_execution = True
        server.enable_health_checks = True
        return server

    @pytest.fixture
    def api_channel(self, channel_config, mock_workflow_server):
        """Create APIChannel instance."""
        return APIChannel(channel_config, workflow_server=mock_workflow_server)

    def test_channel_info_endpoint(self, api_channel):
        """Test channel info endpoint."""
        client = TestClient(api_channel.app)
        response = client.get("/channel/info")

        assert response.status_code == 200
        data = response.json()
        assert data["channel_name"] == "test_api"
        assert data["channel_type"] == "api"
        assert "config" in data

    def test_channel_status_endpoint(self, api_channel):
        """Test channel status endpoint."""
        with patch.object(
            api_channel, "get_status", return_value={"status": "running"}
        ):
            client = TestClient(api_channel.app)
            response = client.get("/channel/status")

            assert response.status_code == 200

    def test_channel_health_endpoint_healthy(self, api_channel):
        """Test channel health endpoint when healthy."""
        with patch.object(api_channel, "health_check", return_value={"healthy": True}):
            client = TestClient(api_channel.app)
            response = client.get("/channel/health")

            assert response.status_code == 200

    def test_channel_health_endpoint_unhealthy(self, api_channel):
        """Test channel health endpoint when unhealthy."""
        with patch.object(api_channel, "health_check", return_value={"healthy": False}):
            client = TestClient(api_channel.app)
            response = client.get("/channel/health")

            assert response.status_code == 503

    def test_emit_event_endpoint_success(self, api_channel):
        """Test emit event endpoint with valid data."""
        with patch.object(api_channel, "emit_event") as mock_emit:
            client = TestClient(api_channel.app)
            event_data = {
                "event_type": "test_event",
                "payload": {"test": "data"},
                "session_id": "session_123",
            }
            response = client.post("/channel/events", json=event_data)

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "event_id" in data
            mock_emit.assert_called_once()

    def test_emit_event_endpoint_error(self, api_channel):
        """Test emit event endpoint with error."""
        with patch.object(
            api_channel, "emit_event", side_effect=Exception("Event error")
        ):
            client = TestClient(api_channel.app)
            response = client.post("/channel/events", json={"invalid": "data"})

            assert response.status_code == 400
            assert "Event error" in response.json()["detail"]
