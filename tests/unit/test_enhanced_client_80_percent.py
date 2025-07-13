"""Comprehensive tests to boost Enhanced Client coverage from 33% to >80%."""

import asyncio
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import aiohttp
import pytest


class TestWorkflowResult:
    """Test WorkflowResult dataclass and properties."""

    def test_workflow_result_initialization(self):
        """Test WorkflowResult initialization."""
        try:
            from kailash.client.enhanced_client import WorkflowResult

            # Test basic initialization
            result = WorkflowResult(
                request_id="req_123",
                workflow_id="wf_456",
                status="completed",
                result={"data": "success"},
                error=None,
                execution_time=1.5,
            )

            assert result.request_id == "req_123"
            assert result.workflow_id == "wf_456"
            assert result.status == "completed"
            assert result.result == {"data": "success"}
            assert result.error is None
            assert result.execution_time == 1.5

        except ImportError:
            pytest.skip("WorkflowResult not available")

    def test_workflow_result_status_properties(self):
        """Test WorkflowResult status check properties."""
        try:
            from kailash.client.enhanced_client import WorkflowResult

            # Test successful status
            success_result = WorkflowResult(
                request_id="req_123", workflow_id="wf_456", status="completed"
            )

            assert success_result.is_success is True
            assert success_result.is_failed is False
            assert success_result.is_running is False

            # Test failed status
            failed_result = WorkflowResult(
                request_id="req_123",
                workflow_id="wf_456",
                status="failed",
                error="Execution failed",
            )

            assert failed_result.is_success is False
            assert failed_result.is_failed is True
            assert failed_result.is_running is False

            # Test pending status
            pending_result = WorkflowResult(
                request_id="req_123", workflow_id="wf_456", status="pending"
            )

            assert pending_result.is_success is False
            assert pending_result.is_failed is False
            assert pending_result.is_running is True

            # Test running status
            running_result = WorkflowResult(
                request_id="req_123", workflow_id="wf_456", status="running"
            )

            assert running_result.is_success is False
            assert running_result.is_failed is False
            assert running_result.is_running is True

        except ImportError:
            pytest.skip("WorkflowResult not available")


class TestKailashClientInitialization:
    """Test KailashClient initialization and setup."""

    def test_client_initialization_basic(self):
        """Test basic client initialization."""
        try:
            from kailash.client.enhanced_client import KailashClient

            client = KailashClient("http://localhost:8000")

            assert client.base_url == "http://localhost:8000"
            assert client.api_key is None
            assert client.timeout == 30
            assert client._session is None

        except ImportError:
            pytest.skip("KailashClient not available")

    def test_client_initialization_with_options(self):
        """Test client initialization with all options."""
        try:
            from kailash.client.enhanced_client import KailashClient

            client = KailashClient(
                "http://api.example.com/",  # With trailing slash
                api_key="test_key_123",
                timeout=60,
            )

            assert client.base_url == "http://api.example.com"  # Trailing slash removed
            assert client.api_key == "test_key_123"
            assert client.timeout == 60
            assert client._session is None

        except ImportError:
            pytest.skip("KailashClient not available")

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Test async context manager protocol."""
        try:
            from kailash.client.enhanced_client import KailashClient

            with patch("aiohttp.ClientSession") as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value = mock_session

                async with KailashClient(
                    "http://localhost:8000", api_key="test"
                ) as client:
                    # Should have created session
                    assert client._session is not None

                # Should have closed session
                mock_session.close.assert_called_once()

        except ImportError:
            pytest.skip("KailashClient not available")

    @pytest.mark.asyncio
    async def test_ensure_session_without_api_key(self):
        """Test session creation without API key."""
        try:
            from kailash.client.enhanced_client import KailashClient

            client = KailashClient("http://localhost:8000")

            with patch("aiohttp.ClientSession") as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value = mock_session

                await client._ensure_session()

                # Should create session with timeout but no auth headers
                mock_session_class.assert_called_once()
                call_kwargs = mock_session_class.call_args.kwargs
                assert "headers" in call_kwargs
                assert call_kwargs["headers"] == {}
                assert "timeout" in call_kwargs

        except ImportError:
            pytest.skip("KailashClient not available")

    @pytest.mark.asyncio
    async def test_ensure_session_with_api_key(self):
        """Test session creation with API key."""
        try:
            from kailash.client.enhanced_client import KailashClient

            client = KailashClient("http://localhost:8000", api_key="test_key")

            with patch("aiohttp.ClientSession") as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value = mock_session

                await client._ensure_session()

                # Should create session with auth headers
                call_kwargs = mock_session_class.call_args.kwargs
                assert call_kwargs["headers"]["Authorization"] == "Bearer test_key"

        except ImportError:
            pytest.skip("KailashClient not available")

    @pytest.mark.asyncio
    async def test_ensure_session_already_exists(self):
        """Test that _ensure_session doesn't recreate existing session."""
        try:
            from kailash.client.enhanced_client import KailashClient

            client = KailashClient("http://localhost:8000")

            # Set existing session
            existing_session = AsyncMock()
            client._session = existing_session

            with patch("aiohttp.ClientSession") as mock_session_class:
                await client._ensure_session()

                # Should not create new session
                mock_session_class.assert_not_called()
                assert client._session is existing_session

        except ImportError:
            pytest.skip("KailashClient not available")

    @pytest.mark.asyncio
    async def test_close_session(self):
        """Test closing session."""
        try:
            from kailash.client.enhanced_client import KailashClient

            client = KailashClient("http://localhost:8000")

            # Set session
            mock_session = AsyncMock()
            client._session = mock_session

            await client.close()

            # Should close and clear session
            mock_session.close.assert_called_once()
            assert client._session is None

        except ImportError:
            pytest.skip("KailashClient not available")

    @pytest.mark.asyncio
    async def test_close_no_session(self):
        """Test closing when no session exists."""
        try:
            from kailash.client.enhanced_client import KailashClient

            client = KailashClient("http://localhost:8000")

            # Should not raise error
            await client.close()
            assert client._session is None

        except ImportError:
            pytest.skip("KailashClient not available")


class TestKailashClientWorkflowExecution:
    """Test workflow execution functionality."""

    @pytest.mark.asyncio
    async def test_execute_workflow_basic(self):
        """Test basic workflow execution."""
        try:
            from kailash.client.enhanced_client import KailashClient, WorkflowResult

            client = KailashClient("http://localhost:8000")

            # Mock session and response with async context manager using MagicMock
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.json = AsyncMock(
                return_value={
                    "request_id": "req_123",
                    "workflow_id": "wf_456",
                    "status": "completed",
                    "result": {"data": "success"},
                }
            )
            mock_response.raise_for_status = Mock()

            # Use MagicMock for proper async context manager protocol
            from unittest.mock import MagicMock

            mock_session.post = MagicMock()
            mock_session.post.return_value.__aenter__ = AsyncMock(
                return_value=mock_response
            )
            mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)

            client._session = mock_session

            # Execute workflow
            result = await client.execute_workflow(
                "wf_456", {"input": "data"}, wait=False  # Don't wait for completion
            )

            # Verify request
            mock_session.post.assert_called_once_with(
                "http://localhost:8000/api/v1/workflows/wf_456/execute",
                json={"inputs": {"input": "data"}, "resources": {}, "context": {}},
            )

            # Verify result
            assert isinstance(result, WorkflowResult)
            assert result.request_id == "req_123"
            assert result.workflow_id == "wf_456"
            assert result.status == "completed"
            assert result.result == {"data": "success"}

        except ImportError:
            pytest.skip("KailashClient not available")

    @pytest.mark.asyncio
    async def test_execute_workflow_with_resources_and_context(self):
        """Test workflow execution with resources and context."""
        try:
            from kailash.client.enhanced_client import KailashClient

            client = KailashClient("http://localhost:8000")

            # Mock session and response with async context manager using MagicMock
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.json = AsyncMock(
                return_value={
                    "request_id": "req_123",
                    "workflow_id": "wf_456",
                    "status": "completed",
                }
            )
            mock_response.raise_for_status = Mock()

            # Use MagicMock for proper async context manager protocol
            from unittest.mock import MagicMock

            mock_session.post = MagicMock()
            mock_session.post.return_value.__aenter__ = AsyncMock(
                return_value=mock_response
            )
            mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)

            client._session = mock_session

            # Execute with resources and context
            await client.execute_workflow(
                "wf_456",
                {"input": "data"},
                resources={"db": {"type": "postgresql"}},
                context={"user_id": "123"},
                wait=False,
            )

            # Verify request data
            call_args = mock_session.post.call_args
            json_data = call_args.kwargs["json"]
            assert json_data["inputs"] == {"input": "data"}
            assert json_data["resources"] == {"db": {"type": "postgresql"}}
            assert json_data["context"] == {"user_id": "123"}

        except ImportError:
            pytest.skip("KailashClient not available")

    @pytest.mark.asyncio
    async def test_execute_workflow_with_wait(self):
        """Test workflow execution with waiting for completion."""
        try:
            from kailash.client.enhanced_client import KailashClient, WorkflowResult

            client = KailashClient("http://localhost:8000")

            # Mock session and responses with async context managers using MagicMock
            mock_session = AsyncMock()

            # Initial response (running)
            mock_initial_response = AsyncMock()
            mock_initial_response.json = AsyncMock(
                return_value={
                    "request_id": "req_123",
                    "workflow_id": "wf_456",
                    "status": "running",
                }
            )
            mock_initial_response.raise_for_status = Mock()

            # Final response (completed)
            mock_final_response = AsyncMock()
            mock_final_response.json = AsyncMock(
                return_value={
                    "request_id": "req_123",
                    "workflow_id": "wf_456",
                    "status": "completed",
                    "result": {"data": "success"},
                }
            )
            mock_final_response.raise_for_status = Mock()

            # Use MagicMock for proper async context manager protocol
            from unittest.mock import MagicMock

            mock_session.post = MagicMock()
            mock_session.post.return_value.__aenter__ = AsyncMock(
                return_value=mock_initial_response
            )
            mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_session.get = MagicMock()
            mock_session.get.return_value.__aenter__ = AsyncMock(
                return_value=mock_final_response
            )
            mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

            client._session = mock_session

            # Mock wait_for_completion to return completed result
            with patch.object(
                client,
                "wait_for_completion",
                return_value=WorkflowResult(
                    request_id="req_123",
                    workflow_id="wf_456",
                    status="completed",
                    result={"data": "success"},
                ),
            ) as mock_wait:

                result = await client.execute_workflow(
                    "wf_456",
                    {"input": "data"},
                    wait=True,
                    poll_interval=0.5,
                    max_wait=60.0,
                )

                # Should have called wait_for_completion
                mock_wait.assert_called_once_with(
                    "wf_456", "req_123", poll_interval=0.5, max_wait=60.0
                )

                assert result.status == "completed"
                assert result.result == {"data": "success"}

        except ImportError:
            pytest.skip("KailashClient not available")

    @pytest.mark.asyncio
    async def test_wait_for_completion_success(self):
        """Test waiting for workflow completion - success case."""
        try:
            from kailash.client.enhanced_client import KailashClient, WorkflowResult

            client = KailashClient("http://localhost:8000")

            # Mock get_workflow_status to return running then completed
            call_count = 0

            async def mock_get_status(workflow_id, request_id):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return WorkflowResult(
                        request_id=request_id, workflow_id=workflow_id, status="running"
                    )
                else:
                    return WorkflowResult(
                        request_id=request_id,
                        workflow_id=workflow_id,
                        status="completed",
                        result={"data": "done"},
                    )

            with patch.object(
                client, "get_workflow_status", side_effect=mock_get_status
            ):
                result = await client.wait_for_completion(
                    "wf_456",
                    "req_123",
                    poll_interval=0.01,  # Very short for testing
                    max_wait=5.0,
                )

                assert result.status == "completed"
                assert result.result == {"data": "done"}
                assert call_count == 2  # Should have polled twice

        except ImportError:
            pytest.skip("KailashClient not available")

    @pytest.mark.asyncio
    async def test_wait_for_completion_timeout(self):
        """Test waiting for workflow completion - timeout case."""
        try:
            from kailash.client.enhanced_client import KailashClient, WorkflowResult

            client = KailashClient("http://localhost:8000")

            # Mock get_workflow_status to always return running
            async def mock_get_status(workflow_id, request_id):
                return WorkflowResult(
                    request_id=request_id, workflow_id=workflow_id, status="running"
                )

            with patch.object(
                client, "get_workflow_status", side_effect=mock_get_status
            ):
                with pytest.raises(TimeoutError) as exc_info:
                    await client.wait_for_completion(
                        "wf_456",
                        "req_123",
                        poll_interval=0.01,
                        max_wait=0.05,  # Very short timeout
                    )

                assert "did not complete within 0.05 seconds" in str(exc_info.value)

        except ImportError:
            pytest.skip("KailashClient not available")

    @pytest.mark.asyncio
    async def test_get_workflow_status(self):
        """Test getting workflow status."""
        try:
            from kailash.client.enhanced_client import KailashClient, WorkflowResult

            client = KailashClient("http://localhost:8000")

            # Mock session and response with async context manager using MagicMock
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.json = AsyncMock(
                return_value={
                    "request_id": "req_123",
                    "workflow_id": "wf_456",
                    "status": "running",
                    "execution_time": 2.5,
                }
            )
            mock_response.raise_for_status = Mock()

            # Use MagicMock for proper async context manager protocol
            from unittest.mock import MagicMock

            mock_session.get = MagicMock()
            mock_session.get.return_value.__aenter__ = AsyncMock(
                return_value=mock_response
            )
            mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

            client._session = mock_session

            result = await client.get_workflow_status("wf_456", "req_123")

            # Verify request
            mock_session.get.assert_called_once_with(
                "http://localhost:8000/api/v1/workflows/wf_456/status/req_123"
            )

            # Verify result
            assert isinstance(result, WorkflowResult)
            assert result.request_id == "req_123"
            assert result.workflow_id == "wf_456"
            assert result.status == "running"
            assert result.execution_time == 2.5

        except ImportError:
            pytest.skip("KailashClient not available")


class TestKailashClientWorkflowManagement:
    """Test workflow management functionality."""

    @pytest.mark.asyncio
    async def test_list_workflows(self):
        """Test listing workflows."""
        try:
            from kailash.client.enhanced_client import KailashClient

            client = KailashClient("http://localhost:8000")

            # Mock session and response with async context manager using MagicMock
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.json = AsyncMock(
                return_value={
                    "workflows": [
                        {"id": "wf_1", "name": "Workflow 1"},
                        {"id": "wf_2", "name": "Workflow 2"},
                    ]
                }
            )
            mock_response.raise_for_status = Mock()

            # Use MagicMock for proper async context manager protocol
            from unittest.mock import MagicMock

            mock_session.get = MagicMock()
            mock_session.get.return_value.__aenter__ = AsyncMock(
                return_value=mock_response
            )
            mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

            client._session = mock_session

            result = await client.list_workflows()

            # Verify request
            mock_session.get.assert_called_once_with(
                "http://localhost:8000/api/v1/workflows"
            )

            # Verify result
            assert result["workflows"][0]["id"] == "wf_1"
            assert len(result["workflows"]) == 2

        except ImportError:
            pytest.skip("KailashClient not available")

    @pytest.mark.asyncio
    async def test_get_workflow_details(self):
        """Test getting workflow details."""
        try:
            from kailash.client.enhanced_client import KailashClient

            client = KailashClient("http://localhost:8000")

            # Mock session and response with async context manager using MagicMock
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.json = AsyncMock(
                return_value={
                    "id": "wf_456",
                    "name": "Test Workflow",
                    "description": "A test workflow",
                    "nodes": ["node1", "node2"],
                }
            )
            mock_response.raise_for_status = Mock()

            # Use MagicMock for proper async context manager protocol
            from unittest.mock import MagicMock

            mock_session.get = MagicMock()
            mock_session.get.return_value.__aenter__ = AsyncMock(
                return_value=mock_response
            )
            mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

            client._session = mock_session

            result = await client.get_workflow_details("wf_456")

            # Verify request
            mock_session.get.assert_called_once_with(
                "http://localhost:8000/api/v1/workflows/wf_456"
            )

            # Verify result
            assert result["id"] == "wf_456"
            assert result["name"] == "Test Workflow"
            assert len(result["nodes"]) == 2

        except ImportError:
            pytest.skip("KailashClient not available")

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health check."""
        try:
            from kailash.client.enhanced_client import KailashClient

            client = KailashClient("http://localhost:8000")

            # Mock session and response with async context manager using MagicMock
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.json = AsyncMock(
                return_value={"status": "healthy", "version": "1.0.0", "uptime": 3600}
            )
            mock_response.raise_for_status = Mock()

            # Use MagicMock for proper async context manager protocol
            from unittest.mock import MagicMock

            mock_session.get = MagicMock()
            mock_session.get.return_value.__aenter__ = AsyncMock(
                return_value=mock_response
            )
            mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

            client._session = mock_session

            result = await client.health_check()

            # Verify request
            mock_session.get.assert_called_once_with(
                "http://localhost:8000/api/v1/health"
            )

            # Verify result
            assert result["status"] == "healthy"
            assert result["version"] == "1.0.0"
            assert result["uptime"] == 3600

        except ImportError:
            pytest.skip("KailashClient not available")

    @pytest.mark.asyncio
    async def test_list_resources(self):
        """Test listing resources."""
        try:
            from kailash.client.enhanced_client import KailashClient

            client = KailashClient("http://localhost:8000")

            # Mock session and response with async context manager using MagicMock
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.json = AsyncMock(
                return_value=["database", "cache", "http_client"]
            )
            mock_response.raise_for_status = Mock()

            # Use MagicMock for proper async context manager protocol
            from unittest.mock import MagicMock

            mock_session.get = MagicMock()
            mock_session.get.return_value.__aenter__ = AsyncMock(
                return_value=mock_response
            )
            mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

            client._session = mock_session

            result = await client.list_resources()

            # Verify request
            mock_session.get.assert_called_once_with(
                "http://localhost:8000/api/v1/resources"
            )

            # Verify result
            assert result == ["database", "cache", "http_client"]

        except ImportError:
            pytest.skip("KailashClient not available")


class TestKailashClientResourceHelpers:
    """Test resource helper methods."""

    def test_ref_helper(self):
        """Test resource reference helper."""
        try:
            from kailash.client.enhanced_client import KailashClient

            client = KailashClient("http://localhost:8000")

            ref = client.ref("my_database")
            assert ref == "@my_database"

        except ImportError:
            pytest.skip("KailashClient not available")

    def test_database_helper_basic(self):
        """Test database resource helper - basic usage."""
        try:
            from kailash.client.enhanced_client import KailashClient

            client = KailashClient("http://localhost:8000")

            db_config = client.database("localhost", "mydb")

            assert db_config["type"] == "database"
            assert db_config["config"]["host"] == "localhost"
            assert db_config["config"]["port"] == 5432  # Default
            assert db_config["config"]["database"] == "mydb"
            assert db_config["credentials_ref"] is None

        except ImportError:
            pytest.skip("KailashClient not available")

    def test_database_helper_with_options(self):
        """Test database resource helper with all options."""
        try:
            from kailash.client.enhanced_client import KailashClient

            client = KailashClient("http://localhost:8000")

            db_config = client.database(
                host="db.example.com",
                database="production_db",
                port=5433,
                credentials_ref="@db_creds",
                schema="public",
                ssl_mode="require",
            )

            assert db_config["type"] == "database"
            assert db_config["config"]["host"] == "db.example.com"
            assert db_config["config"]["port"] == 5433
            assert db_config["config"]["database"] == "production_db"
            assert db_config["config"]["schema"] == "public"
            assert db_config["config"]["ssl_mode"] == "require"
            assert db_config["credentials_ref"] == "@db_creds"

        except ImportError:
            pytest.skip("KailashClient not available")

    def test_http_client_helper_basic(self):
        """Test HTTP client resource helper - basic usage."""
        try:
            from kailash.client.enhanced_client import KailashClient

            client = KailashClient("http://localhost:8000")

            http_config = client.http_client()

            assert http_config["type"] == "http_client"
            assert http_config["config"] == {}
            assert http_config["credentials_ref"] is None

        except ImportError:
            pytest.skip("KailashClient not available")

    def test_http_client_helper_with_options(self):
        """Test HTTP client resource helper with options."""
        try:
            from kailash.client.enhanced_client import KailashClient

            client = KailashClient("http://localhost:8000")

            http_config = client.http_client(
                base_url="https://api.example.com",
                headers={"User-Agent": "KailashClient/1.0"},
                credentials_ref="@api_creds",
                timeout=30,
                verify_ssl=True,
            )

            assert http_config["type"] == "http_client"
            assert http_config["config"]["base_url"] == "https://api.example.com"
            assert http_config["config"]["headers"]["User-Agent"] == "KailashClient/1.0"
            assert http_config["config"]["timeout"] == 30
            assert http_config["config"]["verify_ssl"] is True
            assert http_config["credentials_ref"] == "@api_creds"

        except ImportError:
            pytest.skip("KailashClient not available")

    def test_cache_helper_basic(self):
        """Test cache resource helper - basic usage."""
        try:
            from kailash.client.enhanced_client import KailashClient

            client = KailashClient("http://localhost:8000")

            cache_config = client.cache()

            assert cache_config["type"] == "cache"
            assert cache_config["config"]["host"] == "localhost"
            assert cache_config["config"]["port"] == 6379
            assert cache_config["credentials_ref"] is None

        except ImportError:
            pytest.skip("KailashClient not available")

    def test_cache_helper_with_options(self):
        """Test cache resource helper with options."""
        try:
            from kailash.client.enhanced_client import KailashClient

            client = KailashClient("http://localhost:8000")

            cache_config = client.cache(
                host="redis.example.com",
                port=6380,
                credentials_ref="@redis_creds",
                db=1,
                ssl=True,
            )

            assert cache_config["type"] == "cache"
            assert cache_config["config"]["host"] == "redis.example.com"
            assert cache_config["config"]["port"] == 6380
            assert cache_config["config"]["db"] == 1
            assert cache_config["config"]["ssl"] is True
            assert cache_config["credentials_ref"] == "@redis_creds"

        except ImportError:
            pytest.skip("KailashClient not available")


class TestSyncKailashClient:
    """Test synchronous wrapper client."""

    def test_sync_client_initialization(self):
        """Test synchronous client initialization."""
        try:
            from kailash.client.enhanced_client import KailashClient, SyncKailashClient

            sync_client = SyncKailashClient("http://localhost:8000", api_key="test_key")

            assert isinstance(sync_client.async_client, KailashClient)
            assert sync_client.async_client.base_url == "http://localhost:8000"
            assert sync_client.async_client.api_key == "test_key"

        except ImportError:
            pytest.skip("SyncKailashClient not available")

    def test_sync_execute_workflow(self):
        """Test synchronous workflow execution."""
        try:
            from kailash.client.enhanced_client import SyncKailashClient, WorkflowResult

            sync_client = SyncKailashClient("http://localhost:8000")

            # Mock the async client method
            expected_result = WorkflowResult(
                request_id="req_123", workflow_id="wf_456", status="completed"
            )

            with patch.object(
                sync_client.async_client,
                "execute_workflow",
                return_value=expected_result,
            ) as mock_execute:
                result = sync_client.execute_workflow(
                    "wf_456", {"input": "data"}, resources={"db": "config"}, wait=True
                )

                # Verify async method was called with correct args
                mock_execute.assert_called_once()
                call_args = mock_execute.call_args
                assert call_args[0][0] == "wf_456"  # workflow_id
                assert call_args[0][1] == {"input": "data"}  # inputs
                assert call_args[1]["resources"] == {"db": "config"}
                assert call_args[1]["wait"] is True

                assert result == expected_result

        except ImportError:
            pytest.skip("SyncKailashClient not available")

    def test_sync_list_workflows(self):
        """Test synchronous list workflows."""
        try:
            from kailash.client.enhanced_client import SyncKailashClient

            sync_client = SyncKailashClient("http://localhost:8000")

            expected_result = {"workflows": [{"id": "wf_1"}]}

            with patch.object(
                sync_client.async_client, "list_workflows", return_value=expected_result
            ) as mock_list:
                result = sync_client.list_workflows()

                mock_list.assert_called_once()
                assert result == expected_result

        except ImportError:
            pytest.skip("SyncKailashClient not available")

    def test_sync_get_workflow_details(self):
        """Test synchronous get workflow details."""
        try:
            from kailash.client.enhanced_client import SyncKailashClient

            sync_client = SyncKailashClient("http://localhost:8000")

            expected_result = {"id": "wf_456", "name": "Test Workflow"}

            with patch.object(
                sync_client.async_client,
                "get_workflow_details",
                return_value=expected_result,
            ) as mock_get:
                result = sync_client.get_workflow_details("wf_456")

                mock_get.assert_called_once_with("wf_456")
                assert result == expected_result

        except ImportError:
            pytest.skip("SyncKailashClient not available")

    def test_sync_health_check(self):
        """Test synchronous health check."""
        try:
            from kailash.client.enhanced_client import SyncKailashClient

            sync_client = SyncKailashClient("http://localhost:8000")

            expected_result = {"status": "healthy"}

            with patch.object(
                sync_client.async_client, "health_check", return_value=expected_result
            ) as mock_health:
                result = sync_client.health_check()

                mock_health.assert_called_once()
                assert result == expected_result

        except ImportError:
            pytest.skip("SyncKailashClient not available")

    def test_sync_list_resources(self):
        """Test synchronous list resources."""
        try:
            from kailash.client.enhanced_client import SyncKailashClient

            sync_client = SyncKailashClient("http://localhost:8000")

            expected_result = ["database", "cache"]

            with patch.object(
                sync_client.async_client, "list_resources", return_value=expected_result
            ) as mock_list:
                result = sync_client.list_resources()

                mock_list.assert_called_once()
                assert result == expected_result

        except ImportError:
            pytest.skip("SyncKailashClient not available")

    def test_sync_client_getattr_delegation(self):
        """Test that sync client delegates attribute access to async client."""
        try:
            from kailash.client.enhanced_client import SyncKailashClient

            sync_client = SyncKailashClient("http://localhost:8000")

            # Test delegating to ref method
            ref = sync_client.ref("test_resource")
            assert ref == "@test_resource"

            # Test delegating to database method
            db_config = sync_client.database("localhost", "testdb")
            assert db_config["type"] == "database"
            assert db_config["config"]["host"] == "localhost"

        except ImportError:
            pytest.skip("SyncKailashClient not available")


class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.mark.asyncio
    async def test_http_error_handling(self):
        """Test HTTP error handling."""
        try:
            import aiohttp

            from kailash.client.enhanced_client import KailashClient

            client = KailashClient("http://localhost:8000")

            # Mock session to raise HTTP error with async context manager using MagicMock
            mock_session = AsyncMock()
            mock_response = AsyncMock()

            # Create the exception that will be raised
            error = aiohttp.ClientResponseError(
                request_info=Mock(), history=(), status=404, message="Not Found"
            )
            # Use regular Mock for raise_for_status, not AsyncMock
            mock_response.raise_for_status = Mock(side_effect=error)

            # Use MagicMock for proper async context manager protocol
            from unittest.mock import MagicMock

            mock_session.get = MagicMock()
            mock_session.get.return_value.__aenter__ = AsyncMock(
                return_value=mock_response
            )
            mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

            client._session = mock_session

            with pytest.raises(aiohttp.ClientResponseError):
                await client.list_workflows()

        except ImportError:
            pytest.skip("KailashClient not available")

    @pytest.mark.asyncio
    async def test_timeout_during_wait(self):
        """Test timeout during wait_for_completion."""
        try:
            from kailash.client.enhanced_client import KailashClient, WorkflowResult

            client = KailashClient("http://localhost:8000")

            # Mock to always return running status
            running_result = WorkflowResult(
                request_id="req_123", workflow_id="wf_456", status="running"
            )

            with patch.object(
                client, "get_workflow_status", return_value=running_result
            ):
                with pytest.raises(TimeoutError) as exc_info:
                    await client.wait_for_completion(
                        "wf_456", "req_123", poll_interval=0.01, max_wait=0.03
                    )

                assert "did not complete within 0.03 seconds" in str(exc_info.value)

        except ImportError:
            pytest.skip("KailashClient not available")
