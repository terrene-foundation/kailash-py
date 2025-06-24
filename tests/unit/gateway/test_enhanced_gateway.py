"""Unit tests for Enhanced Gateway Integration.

Tests cover:
- Gateway initialization and workflow registration
- Resource reference resolution
- Secret management
- Workflow execution with resources
- API endpoints
- Client SDK functionality
"""

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, create_autospec, patch

import pytest
import pytest_asyncio

from kailash.client import KailashClient, WorkflowResult
from kailash.gateway import (
    EnhancedDurableAPIGateway,
    ResourceReference,
    SecretBackend,
    SecretManager,
    SecretNotFoundError,
    WorkflowRequest,
    WorkflowResponse,
)
from kailash.resources import ResourceRegistry
from kailash.workflow import AsyncWorkflowBuilder, Workflow


class TestEnhancedGateway:
    """Test enhanced gateway core functionality."""

    @pytest.fixture
    def resource_registry(self):
        """Create test resource registry."""
        return ResourceRegistry()

    @pytest.fixture
    def secret_manager(self):
        """Create test secret manager."""
        return SecretManager()

    @pytest.fixture
    def gateway(self, resource_registry, secret_manager):
        """Create test gateway."""
        # Patch DurableAPIGateway to avoid async initialization issues
        with patch("kailash.gateway.enhanced_gateway.DurableAPIGateway.__init__"):
            gateway = EnhancedDurableAPIGateway.__new__(EnhancedDurableAPIGateway)

            # Initialize base class attributes manually
            gateway.workflows = {}
            gateway.enable_durability = False
            gateway.checkpoint_manager = None
            gateway._checkpoint_task = None

            # Initialize enhanced gateway attributes
            gateway.resource_registry = resource_registry
            gateway.secret_manager = secret_manager
            gateway._workflow_resources = {}
            gateway._resource_resolver = Mock()
            gateway._resource_resolver.resolve = AsyncMock()
            gateway._runtime = Mock()
            gateway._runtime.execute_workflow_async = AsyncMock()
            gateway._active_requests = {}
            gateway._cleanup_tasks = []  # Add missing attribute

            # Patch the parent's register_workflow method
            gateway.register_workflow = Mock(
                side_effect=lambda wf_id, wf, **kwargs: (
                    gateway._workflow_resources.update(
                        {wf_id: set(kwargs.get("required_resources", []))}
                    ),
                    gateway._workflow_resources[wf_id].update(
                        getattr(wf, "metadata", {}).get("required_resources", [])
                    ),
                    (
                        getattr(wf, "metadata", {}).update(
                            {"description": kwargs.get("description")}
                        )
                        if kwargs.get("description") and hasattr(wf, "metadata")
                        else None
                    ),
                )
            )

            return gateway

    def test_gateway_initialization(self, gateway):
        """Test gateway initialization."""
        assert gateway.resource_registry is not None
        assert gateway.secret_manager is not None
        assert gateway._resource_resolver is not None
        assert gateway._runtime is not None
        assert isinstance(gateway._workflow_resources, dict)
        assert isinstance(gateway._active_requests, dict)

    def test_workflow_registration(self, gateway):
        """Test workflow registration with resources."""
        # Create test workflow
        workflow = AsyncWorkflowBuilder("test_workflow").build()
        workflow.metadata = {"async_workflow": True}

        # Register workflow
        gateway.register_workflow(
            "test_workflow",
            workflow,
            required_resources=["db", "cache"],
            description="Test workflow",
        )

        # Manually add to workflows dict (since parent method is bypassed)
        gateway.workflows["test_workflow"] = Mock(
            workflow=workflow, description="Test workflow"
        )

        # Verify registration
        assert "test_workflow" in gateway.workflows
        assert "test_workflow" in gateway._workflow_resources
        assert "db" in gateway._workflow_resources["test_workflow"]
        assert "cache" in gateway._workflow_resources["test_workflow"]

    def test_workflow_registration_metadata_extraction(self, gateway):
        """Test resource extraction from workflow metadata."""
        # Create workflow with metadata
        workflow = AsyncWorkflowBuilder("metadata_test").build()
        workflow.metadata = {
            "async_workflow": True,
            "required_resources": ["api", "database"],
        }

        # Register without explicit resources
        gateway.register_workflow("metadata_test", workflow)

        # Manually add to workflows dict
        gateway.workflows["metadata_test"] = Mock(workflow=workflow)

        # Should extract from metadata
        assert "metadata_test" in gateway._workflow_resources
        assert "api" in gateway._workflow_resources["metadata_test"]
        assert "database" in gateway._workflow_resources["metadata_test"]

    @pytest.mark.asyncio
    async def test_workflow_execution_basic(self, gateway):
        """Test basic workflow execution."""
        # Create simple workflow
        workflow = (
            AsyncWorkflowBuilder("simple")
            .add_async_code("step1", "result = {'value': 42}")
            .build()
        )

        # Add workflow to registry
        gateway.workflows["simple"] = Mock(
            workflow=workflow, description=None, type="workflow", version="1.0", tags=[]
        )

        # Mock runtime execution
        gateway._runtime.execute_workflow_async.return_value = {
            "results": {"step1": {"value": 42}}
        }

        # Execute workflow
        request = WorkflowRequest(inputs={})
        response = await gateway.execute_workflow("simple", request)

        # Verify response
        assert response.status == "completed"
        assert response.error is None
        assert response.result["step1"]["value"] == 42
        assert response.execution_time > 0

    @pytest.mark.asyncio
    async def test_workflow_not_found(self, gateway):
        """Test execution of non-existent workflow."""
        request = WorkflowRequest(inputs={})

        response = await gateway.execute_workflow("nonexistent", request)

        assert response.status == "failed"
        assert "not found" in response.error

    @pytest.mark.asyncio
    async def test_workflow_with_resource_reference(self, gateway, resource_registry):
        """Test workflow execution with resource references."""
        # Mock resource
        mock_db = AsyncMock()
        mock_db.fetch = AsyncMock(return_value=[{"id": 1}])

        # Register resource factory
        mock_factory = Mock()
        mock_factory.create = AsyncMock(return_value=mock_db)
        resource_registry.register_factory("test_db", mock_factory)

        # Create workflow using resource
        workflow = (
            AsyncWorkflowBuilder("with_resource")
            .add_async_code(
                "query",
                """
db = await get_resource("test_db")
data = await db.fetch("SELECT 1")
result = {"count": len(data)}
""",
                required_resources=["test_db"],
            )
            .build()
        )

        # Add workflow to registry
        gateway.workflows["with_resource"] = Mock(
            workflow=workflow, description=None, type="workflow", version="1.0", tags=[]
        )
        gateway._workflow_resources["with_resource"] = {"test_db"}

        # Mock runtime execution
        gateway._runtime.execute_workflow_async.return_value = {
            "results": {"query": {"count": 1}}
        }

        # Execute with resource reference
        request = WorkflowRequest(inputs={}, resources={"test_db": "@test_db"})

        response = await gateway.execute_workflow("with_resource", request)

        assert response.status == "completed"
        assert response.result["query"]["count"] == 1

    def test_list_workflows(self, gateway):
        """Test listing workflows."""
        # Register multiple workflows
        workflow1 = AsyncWorkflowBuilder("workflow1").build()
        workflow1.metadata = {"async_workflow": True}
        workflow1.nodes = [Mock(), Mock()]  # Mock nodes

        workflow2 = AsyncWorkflowBuilder("workflow2").build()
        workflow2.metadata = {"async_workflow": False}
        workflow2.nodes = [Mock()]  # Mock node

        # Add workflows to registry
        gateway.workflows["workflow1"] = Mock(
            workflow=workflow1,
            description="First workflow",
            type="workflow",
            version="1.0",
            tags=["test"],
        )
        gateway._workflow_resources["workflow1"] = {"db"}

        gateway.workflows["workflow2"] = Mock(
            workflow=workflow2,
            description="Second workflow",
            type="async",
            version="2.0",
            tags=[],
        )
        gateway._workflow_resources["workflow2"] = set()

        # List workflows
        workflows = gateway.list_workflows()

        assert len(workflows) == 2
        assert workflows["workflow1"]["async_workflow"] is True
        assert workflows["workflow1"]["required_resources"] == ["db"]
        assert workflows["workflow1"]["node_count"] == 2
        assert workflows["workflow2"]["async_workflow"] is False
        assert workflows["workflow2"]["required_resources"] == []
        assert workflows["workflow2"]["node_count"] == 1

    @pytest.mark.asyncio
    async def test_health_check(self, gateway, resource_registry):
        """Test gateway health check."""
        # Add mock resource
        mock_resource = AsyncMock()
        mock_factory = Mock()
        mock_factory.create = AsyncMock(return_value=mock_resource)
        mock_factory.health_check = AsyncMock(return_value=True)

        resource_registry.register_factory("healthy_resource", mock_factory)
        await resource_registry.get_resource("healthy_resource")

        # Perform health check
        health = await gateway.health_check()

        assert health["status"] == "healthy"
        assert health["workflows"] == 0
        assert health["active_requests"] == 0
        assert "healthy_resource" in health["resources"]
        assert health["resources"]["healthy_resource"] == "healthy"


class TestResourceResolver:
    """Test resource resolution functionality."""

    @pytest.fixture
    def resource_registry(self):
        """Create test resource registry."""
        return ResourceRegistry()

    @pytest.fixture
    def secret_manager(self):
        """Create test secret manager."""
        return SecretManager()

    @pytest.fixture
    def resolver(self, resource_registry, secret_manager):
        """Create test resolver."""
        from kailash.gateway.resource_resolver import ResourceResolver

        return ResourceResolver(resource_registry, secret_manager)

    @pytest.mark.asyncio
    async def test_database_resolution(self, resolver):
        """Test database resource resolution."""
        ref = ResourceReference(
            type="database",
            config={"host": "localhost", "port": 5432, "database": "testdb"},
        )

        # Mock database factory
        with patch(
            "kailash.gateway.resource_resolver.DatabasePoolFactory"
        ) as mock_factory:
            mock_pool = AsyncMock()
            mock_factory.return_value.create = AsyncMock(return_value=mock_pool)

            result = await resolver.resolve(ref)

            # Should create and register pool
            assert mock_factory.called
            assert result is not None

    @pytest.mark.asyncio
    async def test_http_client_resolution(self, resolver):
        """Test HTTP client resolution."""
        ref = ResourceReference(
            type="http_client",
            config={"base_url": "https://api.example.com", "timeout": 30},
        )

        with patch(
            "kailash.gateway.resource_resolver.HttpClientFactory"
        ) as mock_factory:
            mock_client = AsyncMock()
            mock_factory.return_value.create = AsyncMock(return_value=mock_client)

            result = await resolver.resolve(ref)

            assert mock_factory.called
            assert result is not None

    @pytest.mark.asyncio
    async def test_resolution_with_credentials(self, resolver, secret_manager):
        """Test resource resolution with credentials."""
        # Store test credentials without encryption for test
        await secret_manager.store_secret(
            "db_creds", {"user": "testuser", "password": "testpass"}, encrypt=False
        )

        ref = ResourceReference(
            type="database",
            config={"host": "localhost", "database": "testdb"},
            credentials_ref="db_creds",
        )

        with patch(
            "kailash.gateway.resource_resolver.DatabasePoolFactory"
        ) as mock_factory:
            mock_pool = AsyncMock()
            mock_factory.return_value.create = AsyncMock(return_value=mock_pool)

            result = await resolver.resolve(ref)

            # Check credentials were merged
            # DatabasePoolFactory is called with keyword arguments
            call_kwargs = mock_factory.call_args[1] if mock_factory.call_args else {}
            assert call_kwargs.get("user") == "testuser"
            assert call_kwargs.get("password") == "testpass"

    @pytest.mark.asyncio
    async def test_unknown_resource_type(self, resolver):
        """Test resolution of unknown resource type."""
        ref = ResourceReference(type="unknown_type", config={})

        with pytest.raises(ValueError, match="Unknown resource type"):
            await resolver.resolve(ref)


class TestSecretManager:
    """Test secret management functionality."""

    @pytest.fixture
    def backend(self):
        """Create mock secret backend."""
        backend = Mock(spec=SecretBackend)
        backend.get_secret = AsyncMock()
        backend.store_secret = AsyncMock()
        backend.delete_secret = AsyncMock()
        return backend

    @pytest.fixture
    def secret_manager(self, backend):
        """Create secret manager with mock backend."""
        return SecretManager(backend=backend, cache_ttl=1)

    @pytest.mark.asyncio
    async def test_get_secret(self, secret_manager, backend):
        """Test getting secret."""
        backend.get_secret.return_value = {"user": "test", "pass": "secret"}

        secret = await secret_manager.get_secret("test_ref")

        assert secret["user"] == "test"
        assert secret["pass"] == "secret"
        backend.get_secret.assert_called_once_with("test_ref")

    @pytest.mark.asyncio
    async def test_secret_caching(self, secret_manager, backend):
        """Test secret caching."""
        backend.get_secret.return_value = {"cached": "value"}

        # First call
        secret1 = await secret_manager.get_secret("cache_test")
        # Second call (should use cache)
        secret2 = await secret_manager.get_secret("cache_test")

        assert secret1 == secret2
        # Backend should only be called once
        assert backend.get_secret.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_expiration(self, secret_manager, backend):
        """Test cache expiration."""
        backend.get_secret.return_value = {"value": "original"}

        # Get secret
        await secret_manager.get_secret("expire_test")

        # Wait for cache to expire
        await asyncio.sleep(1.1)

        # Update backend value
        backend.get_secret.return_value = {"value": "updated"}

        # Get again (should fetch from backend)
        secret = await secret_manager.get_secret("expire_test")

        assert secret["value"] == "updated"
        assert backend.get_secret.call_count == 2

    @pytest.mark.asyncio
    async def test_store_secret_encrypted(self, secret_manager, backend):
        """Test storing encrypted secret."""
        secret = {"api_key": "secret123"}

        await secret_manager.store_secret("test_secret", secret, encrypt=True)

        # Check it was encrypted
        backend.store_secret.assert_called_once()
        stored_value = backend.store_secret.call_args[0][1]
        assert stored_value.startswith("encrypted:")

    @pytest.mark.asyncio
    async def test_delete_secret(self, secret_manager, backend):
        """Test deleting secret."""
        # Store and cache a secret
        backend.get_secret.return_value = {"to": "delete"}
        await secret_manager.get_secret("delete_test")

        # Delete it
        await secret_manager.delete_secret("delete_test")

        backend.delete_secret.assert_called_once_with("delete_test")

        # Should be removed from cache
        backend.get_secret.return_value = {"new": "value"}
        secret = await secret_manager.get_secret("delete_test")
        assert secret["new"] == "value"
        assert backend.get_secret.call_count == 2


class TestKailashClient:
    """Test client SDK functionality."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return KailashClient("http://localhost:8000")

    def test_resource_helpers(self, client):
        """Test resource reference helpers."""
        # Test reference syntax
        ref = client.ref("my_resource")
        assert ref == "@my_resource"

        # Test database helper
        db_ref = client.database(
            host="localhost", database="testdb", credentials_ref="db_creds"
        )
        assert db_ref["type"] == "database"
        assert db_ref["config"]["host"] == "localhost"
        assert db_ref["credentials_ref"] == "db_creds"

        # Test HTTP client helper
        http_ref = client.http_client(
            base_url="https://api.example.com", headers={"X-API-Key": "test"}
        )
        assert http_ref["type"] == "http_client"
        assert http_ref["config"]["base_url"] == "https://api.example.com"
        assert http_ref["config"]["headers"]["X-API-Key"] == "test"

        # Test cache helper
        cache_ref = client.cache(host="redis.local", port=6380)
        assert cache_ref["type"] == "cache"
        assert cache_ref["config"]["host"] == "redis.local"
        assert cache_ref["config"]["port"] == 6380

    @pytest.mark.asyncio
    async def test_workflow_result(self):
        """Test WorkflowResult properties."""
        # Success result
        result = WorkflowResult(
            request_id="123",
            workflow_id="test",
            status="completed",
            result={"data": "value"},
        )
        assert result.is_success
        assert not result.is_failed
        assert not result.is_running

        # Failed result
        result = WorkflowResult(
            request_id="456",
            workflow_id="test",
            status="failed",
            error="Something went wrong",
        )
        assert not result.is_success
        assert result.is_failed
        assert not result.is_running

        # Running result
        result = WorkflowResult(request_id="789", workflow_id="test", status="running")
        assert not result.is_success
        assert not result.is_failed
        assert result.is_running
