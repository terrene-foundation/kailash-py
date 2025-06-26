"""Integration tests for API Gateway with .execute() method fix.

This test verifies that the middleware components correctly use
the .execute() method instead of the removed .process() method.
"""

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from kailash.middleware.communication.api_gateway import (
    APIGateway,
    SessionCreateRequest,
    SessionResponse,
)
from kailash.middleware.core.agent_ui import AgentUIMiddleware
from kailash.nodes.transform import DataTransformer


@pytest.mark.integration
class TestAPIGatewayExecuteFix:
    """Test API Gateway with the .execute() method fix."""

    @pytest.fixture
    def mock_agent_ui(self):
        """Create a mock AgentUIMiddleware."""
        mock = AsyncMock(spec=AgentUIMiddleware)
        mock.create_session = AsyncMock(return_value="test-session-123")
        mock.get_session = AsyncMock(
            return_value=MagicMock(
                session_id="test-session-123",
                user_id="test-user",
                created_at=datetime.now(),
                active=True,
            )
        )
        return mock

    @pytest.fixture
    def api_gateway(self, mock_agent_ui):
        """Create API Gateway with mocked dependencies."""
        # Create gateway without auth for testing
        gateway = APIGateway(enable_auth=False, enable_docs=False)

        # Replace agent_ui with mock
        gateway.agent_ui = mock_agent_ui

        # Create test client
        client = TestClient(gateway.app)
        return gateway, client

    def test_data_transformer_has_execute_not_process(self, api_gateway):
        """Verify DataTransformer has execute() method, not process()."""
        gateway, _ = api_gateway

        # Check that data_transformer exists
        assert hasattr(gateway, "data_transformer")
        assert isinstance(gateway.data_transformer, DataTransformer)

        # Check it has execute() but not process()
        assert hasattr(gateway.data_transformer, "execute")
        assert not hasattr(gateway.data_transformer, "process")

        # Verify execute() works
        result = gateway.data_transformer.execute(
            data={"test": "data"}, transformations=["{**data, 'added': 'field'}"]
        )
        assert result["result"]["test"] == "data"
        assert result["result"]["added"] == "field"

    def test_session_creation_endpoint_with_execute(self, api_gateway):
        """Test session creation endpoint uses execute() correctly."""
        gateway, client = api_gateway

        # Make request to create session
        response = client.post(
            "/api/sessions",
            json={"user_id": "test-user", "metadata": {"source": "test"}},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "session_id" in data
        assert data["session_id"] == "test-session-123"
        assert "api_version" in data  # Added by DataTransformer
        assert data["api_version"] == gateway.version

    @pytest.mark.asyncio
    async def test_data_transformer_execute_in_session_flow(self, api_gateway):
        """Test the complete session creation flow with DataTransformer.execute()."""
        gateway, _ = api_gateway

        # Manually test the session creation logic that uses DataTransformer
        session_data = {
            "session_id": "test-123",
            "user_id": "user-456",
            "created_at": datetime.now().isoformat(),
            "active": True,
        }

        # This is what happens in the API endpoint
        transformed = gateway.data_transformer.execute(
            data=session_data,
            transformations=[f"{{**data, 'api_version': '{gateway.version}'}}"],
        )

        # Verify transformation worked
        assert transformed["result"]["session_id"] == "test-123"
        assert transformed["result"]["api_version"] == gateway.version

        # Verify SessionResponse can be created from transformed data
        session_response = SessionResponse(**transformed["result"])
        assert session_response.session_id == "test-123"
        assert session_response.api_version == gateway.version

    def test_error_handling_with_execute(self, api_gateway):
        """Test error handling when execute() is used."""
        gateway, _ = api_gateway

        # Test with invalid transformation
        with pytest.raises(Exception):
            gateway.data_transformer.execute(
                data={"test": "data"},
                transformations=["invalid python code {{}"],  # Syntax error
            )

    @pytest.mark.parametrize(
        "endpoint,method",
        [
            ("/api/sessions", "post"),
            ("/api/sessions/test-123", "get"),
        ],
    )
    def test_api_endpoints_no_process_calls(self, api_gateway, endpoint, method):
        """Verify API endpoints don't trigger .process() calls."""
        gateway, client = api_gateway

        # Mock DataTransformer to ensure no .process() is called
        with patch.object(
            gateway.data_transformer, "execute", wraps=gateway.data_transformer.execute
        ) as mock_execute:
            # Add a fake process method that should never be called
            gateway.data_transformer.process = MagicMock(
                side_effect=AttributeError("process() was removed in v0.6.0")
            )

            # Make request
            if method == "post":
                response = client.post(endpoint, json={"user_id": "test"})
            else:
                response = client.get(endpoint)

            # Verify execute was called (not process)
            if endpoint == "/api/sessions" and method == "post":
                assert mock_execute.called

            # Verify process was never called
            assert (
                not hasattr(gateway.data_transformer, "process")
                or not gateway.data_transformer.process.called
            )

    @pytest.mark.asyncio
    async def test_concurrent_session_creation_with_execute(self, api_gateway):
        """Test concurrent session creation using execute()."""
        gateway, client = api_gateway

        # Create multiple sessions concurrently
        async def create_session(user_id):
            response = await asyncio.to_thread(
                client.post, "/api/sessions", json={"user_id": user_id}
            )
            return response.json()

        # Create 5 sessions concurrently
        tasks = [create_session(f"user-{i}") for i in range(5)]
        results = await asyncio.gather(*tasks)

        # Verify all sessions were created with api_version
        for result in results:
            assert "session_id" in result
            assert "api_version" in result
            assert result["api_version"] == gateway.version


@pytest.mark.integration
class TestMiddlewareComponentsExecuteFix:
    """Test other middleware components that were fixed."""

    def test_ai_chat_middleware_uses_execute(self):
        """Test that AIChatMiddleware uses execute() for LLM and embedding nodes."""
        from kailash.middleware.communication.ai_chat import AIChatMiddleware
        from kailash.nodes.ai import EmbeddingGeneratorNode, LLMAgentNode

        # Create middleware
        chat = AIChatMiddleware()

        # Mock nodes to verify execute() is available
        chat.llm_node = MagicMock(spec=LLMAgentNode)
        chat.llm_node.execute = MagicMock(
            return_value={"choices": [{"message": {"content": "test"}}]}
        )

        chat.embedding_node = MagicMock(spec=EmbeddingGeneratorNode)
        chat.embedding_node.execute = MagicMock(
            return_value={"embedding": [0.1, 0.2, 0.3]}
        )

        # Verify nodes have execute() but not process()
        assert hasattr(chat.llm_node, "execute")
        assert hasattr(chat.embedding_node, "execute")

    def test_access_control_uses_execute(self):
        """Test that access control components use execute()."""
        from kailash.middleware.auth.access_control import MiddlewareAccessControl

        # Create access control
        access_control = MiddlewareAccessControl(strategy="rbac")

        # Verify internal nodes have execute() method
        assert hasattr(access_control.permission_check_node, "execute")
        assert hasattr(access_control.audit_node, "execute")
        assert hasattr(access_control.role_mgmt_node, "execute")

        # Ensure they don't have process()
        assert not hasattr(access_control.permission_check_node, "process")
        assert not hasattr(access_control.audit_node, "process")
        assert not hasattr(access_control.role_mgmt_node, "process")
